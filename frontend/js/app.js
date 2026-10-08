/* Vortex – vanilla JS frontend talking to the Django JSON API (same origin). */
(function () {
  "use strict";

  var API_BASE = window.VORTEX_API_BASE || "/api";
  var FILTERS = ["For You", "Following", "Explore"];
  var FILTER_KEY = { "For You": "for-you", "Following": "following", "Explore": "explore" };

  var state = {
    me: null, profile: null,
    posts: [], hasMore: false, postsLoading: false, postsError: "",
    stories: [], notifications: [], unread: 0,
    filter: "For You", tab: "Feed", query: "", page: "home"  /* home | profile */
  };

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };
  var els = {
    topbar: $(".topbar"), brandLogo: $("#brandLogo"),
    searchForm: $("#searchForm"), searchInput: $("#searchInput"), searchBtn: $("#searchBtn"),
    addBtn: $("#addBtn"), themeBtn: $("#themeBtn"), bellBtn: $("#bellBtn"), badge: $("#notifBadge"),
    panel: $("#notifPanel"), notifList: $("#notifList"),
    profile: $("#profile"), profilePage: $("#profilePage"),
    stories: $("#stories"), storiesWrap: $("#storiesSection"),
    filters: $("#filters"), feed: $("#feed"),
    bottomNav: $("#bottomNav"), navAvatar: $("#navAvatar"),
    viewer: $("#viewer"), dialog: $("#dialog"), toasts: $("#toasts")
  };

  /* ================= helpers ================= */
  function esc(str) {
    return String(str == null ? "" : str).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  var fmt = function (n) { return Number(n).toLocaleString("en-US"); };
  var ago = function (t) { return t === "now" ? "now" : t + " ago"; };
  var isMe = function () { return state.me && state.profile && state.profile.id === state.me.id; };
  var findPost = function (id) { return state.posts.filter(function (p) { return String(p.id) === String(id); })[0]; };

  /* Avatar with initials fallback (users without a picture) */
  function av(u) {
    if (u && u.avatar) return u.avatar;
    var ch = ((u && (u.name || u.username)) || "?").trim().charAt(0).toUpperCase();
    var svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">' +
      '<stop offset="0" stop-color="#8b5cf6"/><stop offset="1" stop-color="#c026d3"/></linearGradient></defs>' +
      '<rect width="64" height="64" fill="url(#g)"/><text x="32" y="43" font-size="30" font-family="sans-serif" font-weight="700" text-anchor="middle" fill="#fff">' +
      esc(ch) + "</text></svg>";
    return "data:image/svg+xml," + encodeURIComponent(svg);
  }

  function toast(msg) {
    var t = document.createElement("div");
    t.className = "toast";
    t.textContent = msg;
    els.toasts.appendChild(t);
    setTimeout(function () {
      t.classList.add("is-leaving");
      setTimeout(function () { t.remove(); }, 300);
    }, 2400);
  }

  function getTheme() {
    try { return localStorage.getItem("vortex-theme") || "dark"; } catch (e) { return "dark"; }
  }
  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme === "light" ? "light" : "dark");
    if (els.themeBtn) {
      els.themeBtn.innerHTML = icon(theme === "light" ? "moon" : "sun", 20);
      els.themeBtn.setAttribute("aria-label", theme === "light" ? "Switch to dark mode" : "Switch to light mode");
      els.themeBtn.title = theme === "light" ? "Dark mode" : "Light mode";
    }
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", theme === "light" ? "#f8fafc" : "#020617");
  }
  function initTheme() {
    applyTheme(getTheme());
  }
  function toggleTheme() {
    var next = getTheme() === "light" ? "dark" : "light";
    try { localStorage.setItem("vortex-theme", next); } catch (e) {}
    applyTheme(next);
  }

  /* ================= API layer ================= */
  function getCookie(name) {
    var m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
    return m ? decodeURIComponent(m[1]) : "";
  }

  function api(path, opts) {
    opts = opts || {};
    var init = { method: opts.method || "GET", credentials: "same-origin", headers: { Accept: "application/json" } };
    if (opts.formData) {
      init.body = opts.formData;
    } else if (opts.body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(opts.body);
    }
    if (init.method !== "GET") init.headers["X-CSRFToken"] = getCookie("csrftoken");
    return fetch(API_BASE + path, init).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok) {
          var err = new Error(data.error || "Something went wrong (" + res.status + ")");
          err.status = res.status;
          if (res.status === 401 && !opts.quiet401) { state.me = null; showAuth("login"); }
          throw err;
        }
        return data;
      });
    });
  }

  function filePreview(input, imgEl) {
    if (!input.files || !input.files[0]) { if (imgEl) imgEl.hidden = true; return; }
    var url = URL.createObjectURL(input.files[0]);
    if (imgEl) { imgEl.src = url; imgEl.hidden = false; }
  }

  /* ================= header ================= */
  function initHeader() {
    els.brandLogo.innerHTML = icon("vortex", 20);
    els.searchBtn.innerHTML = icon("search", 20);
    els.addBtn.innerHTML = icon("plus", 22);
    els.bellBtn.innerHTML = icon("bell", 20);
    initTheme();
    if (els.themeBtn) {
      els.themeBtn.addEventListener("click", function () { toggleTheme(); });
    }
    // Bottom nav icons
    $$("[data-ico]", els.bottomNav).forEach(function (el) {
      var name = el.dataset.ico;
      el.innerHTML = icon(name === "plus" ? "plus" : name, name === "plus" ? 24 : 22);
    });

    els.addBtn.addEventListener("click", function () { if (state.me) openComposer(); });

    els.searchBtn.addEventListener("click", function () {
      var open = els.searchForm.hidden;
      els.searchForm.hidden = !open;
      els.topbar.classList.toggle("is-searching", open);
      els.searchBtn.setAttribute("aria-expanded", String(open));
      if (open) els.searchInput.focus();
      else if (state.query) { els.searchInput.value = ""; setQuery(""); }
    });
    els.searchForm.addEventListener("submit", function (e) { e.preventDefault(); els.searchInput.blur(); });
    var timer;
    els.searchInput.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(function () { setQuery(els.searchInput.value); }, 250);
    });

    els.bellBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      var open = els.panel.hidden;
      togglePanel(open);
      if (open && state.unread > 0) {
        api("/notifications/read", { method: "POST" }).then(function () {
          state.unread = 0; renderBadge();
        }).catch(function () {});
      }
    });
    els.panel.addEventListener("click", function (e) { e.stopPropagation(); });
  }

  function togglePanel(open) {
    els.panel.hidden = !open;
    els.bellBtn.setAttribute("aria-expanded", String(open));
  }

  function renderBadge() {
    els.badge.hidden = state.unread === 0;
    els.badge.textContent = state.unread > 99 ? "99+" : state.unread;
  }

  function renderNotifications() {
    renderBadge();
    els.notifList.innerHTML = state.notifications.length ? state.notifications.map(function (n) {
      return '<li><img src="' + esc(av({ avatar: n.avatar, name: n.actor })) + '" alt="" loading="lazy" />' +
        '<div class="notif__text"><p>' + esc(n.text) + "</p><small>" + esc(ago(n.timestamp)) + "</small></div>" +
        (n.unread ? '<span class="dot"></span>' : "") + "</li>";
    }).join("") : '<li><div class="notif__text"><p>No notifications yet.</p></div></li>';
  }

  function loadNotifications() {
    return api("/notifications").then(function (d) {
      state.notifications = d.results; state.unread = d.unreadCount; renderNotifications();
    }).catch(function () {});
  }

  /* ================= profile ================= */
  function tabsFor() { return isMe() ? ["Feed", "Media", "Saved", "Liked"] : ["Feed", "Media"]; }

  function renderProfile() {
    var p = state.profile;
    if (!p) { els.profile.innerHTML = ""; return; }
    var actions;
    if (isMe()) {
      actions =
        '<div class="profile__actions">' +
          '<button class="btn-follow btn-follow--primary" data-edit-profile>' + icon("edit", 14) + " Edit profile</button>" +
          '<button class="btn-follow btn-follow--ghost" data-add-story title="Add story">' + icon("camera", 16) + " Story</button>" +
          '<button class="btn-follow btn-follow--ghost" data-logout>Log out</button>' +
        "</div>";
    } else {
      actions =
        '<div class="profile__actions">' +
          '<button class="btn-follow ' + (p.isFollowing ? "btn-follow--ghost" : "btn-follow--primary") + '" data-follow aria-pressed="' + p.isFollowing + '">' +
            (p.isFollowing ? "Following" : "Follow") + "</button>" +
        "</div>";
    }
    var back = isMe() ? "" :
      '<button class="profile__back" data-back-profile aria-label="Back to my profile">' +
        icon("arrowLeft", 18) + " <span>Back</span></button>";
    els.profile.innerHTML =
      back +
      '<div class="profile__cover">' + (p.coverImage ? '<img src="' + esc(p.coverImage) + '" alt="" />' : "") + "</div>" +
      '<div class="profile__body">' +
        '<div class="profile__top">' +
          '<div class="avatar-ring"><img src="' + esc(av(p)) + '" alt="' + esc(p.name) + '" /><span class="status"></span></div>' + actions +
        "</div>" +
        '<div class="profile__name"><h2>' + esc(p.name) + "</h2>" +
          (p.verified ? '<span class="verified" aria-label="Verified">' + icon("check", 18) + "</span>" : "") + "</div>" +
        '<p class="profile__user">@' + esc(p.username) + "</p>" +
        (p.bio ? '<p class="profile__bio">' + esc(p.bio) + "</p>" : "") +
        '<div class="profile__meta">' +
          (p.location ? "<span>" + icon("pin", 14) + " " + esc(p.location) + "</span>" : "") +
          (p.website ? '<span class="link">' + icon("link", 14) + " " + esc(p.website) + "</span>" : "") +
        "</div>" +
        '<div class="profile__stats">' +
          "<span><strong>" + fmt(p.postsCount) + "</strong>Posts</span>" +
          "<span><strong>" + fmt(p.followersCount) + "</strong>Followers</span>" +
          "<span><strong>" + fmt(p.followingCount) + "</strong>Following</span>" +
        "</div>" +
        '<div class="tabs" role="tablist">' +
          tabsFor().map(function (tabName) {
            return '<button role="tab" data-tab="' + tabName + '" aria-selected="' + (state.tab === tabName) + '">' + tabName + "</button>";
          }).join("") +
        "</div>" +
      "</div>";
  }

  function openProfile(username) {
    if (!username || username === "__me" || (state.me && username === state.me.username)) {
      state.profile = state.me;
      state.page = "profile";
      afterProfileChange();
      return;
    }
    api("/users/" + encodeURIComponent(username)).then(function (u) {
      state.profile = u;
      state.page = "profile";
      afterProfileChange();
      window.scrollTo({ top: 0, behavior: "smooth" });
    }).catch(function (e) { toast(e.message); });
  }

  function goHome() {
    state.page = "home";
    state.profile = state.me;
    state.tab = "Feed";
    state.filter = "For You";
    state.query = "";
    if (els.searchInput) els.searchInput.value = "";
    renderProfile();
    renderChrome();
    renderBottomNav();
    loadPosts();
    loadStories();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function afterProfileChange() {
    state.tab = "Feed"; state.query = ""; els.searchInput.value = "";
    renderProfile(); renderChrome(); renderBottomNav(); loadPosts();
  }

  function toggleFollow() {
    var p = state.profile;
    api("/users/" + encodeURIComponent(p.username) + "/follow", { method: "POST" }).then(function (r) {
      p.isFollowing = r.isFollowing;
      p.followersCount = r.followersCount;
      if (state.me && typeof r.followingCount === "number") {
        state.me.followingCount = r.followingCount;
      }
      renderProfile();
      toast((r.isFollowing ? "Following " : "Unfollowed ") + p.name);
    }).catch(function (e) { toast(e.message); });
  }

  /* ================= stories ================= */
  function renderStories() {
    var addBtn = state.me
      ? '<button class="story story--add" data-add-story aria-label="Add your story">' +
          '<div class="story__ring story__ring--add"><div><img src="' + esc(av(state.me)) + '" alt="" loading="lazy" />' +
          '<span class="story__plus">' + icon("plus", 14) + "</span></div></div>" +
          "<span>Your story</span></button>"
      : "";
    els.stories.innerHTML = addBtn + state.stories.map(function (s) {
      return '<button class="story' + (s.seen ? " is-seen" : "") + '" data-story="' + s.id + '" aria-label="View story by ' + esc(s.user.name) + '">' +
        '<div class="story__ring"><div><img src="' + esc(av(s.user)) + '" alt="" loading="lazy" /></div></div>' +
        "<span>" + esc(s.user.username) + "</span></button>";
    }).join("");
  }

  function loadStories() {
    return api("/stories").then(function (d) { state.stories = d.results; renderStories(); }).catch(function () {});
  }

  function openStory(id) {
    var s = state.stories.filter(function (x) { return String(x.id) === String(id); })[0];
    if (!s) return;
    if (!s.seen) {
      s.seen = true; renderStories();
      api("/stories/" + s.id + "/seen", { method: "POST" }).catch(function () {});
    }
    var media = s.previewImage
      ? '<img class="viewer__img" src="' + esc(s.previewImage) + '" alt="Story by ' + esc(s.user.name) + '" />'
      : '<div class="viewer__img viewer__img--text" aria-hidden="true"></div>';
    var caption = s.text
      ? '<div class="viewer__caption">' + esc(s.text) + "</div>"
      : "";
    var liked = s.isLiked ? " is-on" : "";
    els.viewer.innerHTML =
      '<div class="viewer__card" data-story-id="' + s.id + '">' +
        '<div class="viewer__progress"><i></i></div>' +
        '<div class="viewer__head"><img src="' + esc(av(s.user)) + '" alt="" /><span>' + esc(s.user.name) + "</span>" +
          '<button class="viewer__close" data-close-story aria-label="Close story">' + icon("x", 18) + "</button></div>" +
        media + caption +
        '<div class="viewer__footer">' +
          '<button class="viewer__like' + liked + '" data-story-like="' + s.id + '" aria-label="Like story" aria-pressed="' + !!s.isLiked + '">' +
            icon("heart", 22) +
            '<span data-story-likes data-story-likers="' + s.id + '">' + (s.likesCount || 0) + "</span>" +
          "</button>" +
          '<div class="viewer__reply"><div>Reply to ' + esc(s.user.username) + "…</div></div>" +
        "</div>" +
      "</div>";
    els.viewer.hidden = false;
    document.body.style.overflow = "hidden";
    $(".viewer__progress i", els.viewer).addEventListener("animationend", closeStory);
    $("[data-close-story]", els.viewer).focus();
  }

  function toggleStoryLike(id) {
    var s = state.stories.filter(function (x) { return String(x.id) === String(id); })[0];
    if (!s) return;
    var prevLiked = !!s.isLiked;
    var prevCount = s.likesCount || 0;
    s.isLiked = !prevLiked;
    s.likesCount = prevCount + (s.isLiked ? 1 : -1);
    paintStoryLike(s);
    api("/stories/" + id + "/like", { method: "POST" }).then(function (r) {
      s.isLiked = r.isLiked;
      s.likesCount = r.likesCount;
      paintStoryLike(s);
    }).catch(function (e) {
      s.isLiked = prevLiked;
      s.likesCount = prevCount;
      paintStoryLike(s);
      toast(e.message);
    });
  }

  function paintStoryLike(s) {
    var btn = $('[data-story-like="' + s.id + '"]', els.viewer);
    if (!btn) return;
    btn.classList.toggle("is-on", !!s.isLiked);
    btn.setAttribute("aria-pressed", String(!!s.isLiked));
    var cnt = $("[data-story-likes]", btn);
    if (cnt) {
      cnt.textContent = s.likesCount || 0;
      cnt.setAttribute("data-story-likers", s.id);
    }
  }

  function showStoryLikers(id) {
    // Remove existing sheet
    var old = $(".likers-sheet", els.viewer);
    if (old) old.remove();
    var sheet = document.createElement("div");
    sheet.className = "likers-sheet";
    sheet.innerHTML =
      '<div class="likers-sheet__head"><span>Liked by</span>' +
        '<button class="icon-btn" data-close-likers aria-label="Close">' + icon("x", 18) + "</button></div>" +
      '<div class="likers-sheet__empty">Loading…</div>';
    var card = $(".viewer__card", els.viewer);
    if (card) card.appendChild(sheet);
    else els.viewer.appendChild(sheet);

    api("/stories/" + id + "/likes").then(function (d) {
      // Keep story data in state in case we need it
      if (d.story) {
        var existing = state.stories.filter(function (x) { return String(x.id) === String(id); })[0];
        if (existing) {
          existing.likesCount = d.story.likesCount;
          existing.isLiked = d.story.isLiked;
          existing.text = d.story.text;
          existing.previewImage = d.story.previewImage;
        } else if (d.story) {
          state.stories.push(d.story);
        }
        paintStoryLike(existing || d.story);
      }
      var list = d.results || [];
      if (!list.length) {
        sheet.querySelector(".likers-sheet__empty").textContent = "No likes yet.";
        return;
      }
      sheet.querySelector(".likers-sheet__empty").remove();
      var ul = document.createElement("ul");
      ul.className = "likers-sheet__list";
      ul.innerHTML = list.map(function (u) {
        return '<li data-profile="' + esc(u.username) + '">' +
          '<img src="' + esc(av(u)) + '" alt="" loading="lazy" />' +
          '<div class="meta"><b>' + esc(u.name) + "</b><span>@" + esc(u.username) + "</span></div>" +
          "</li>";
      }).join("");
      sheet.appendChild(ul);
    }).catch(function (e) {
      var empty = sheet.querySelector(".likers-sheet__empty");
      if (empty) empty.textContent = e.message || "Could not load likes.";
    });
  }

  function closeStory() {
    if (els.viewer.hidden) return;
    els.viewer.hidden = true;
    els.viewer.innerHTML = "";
    if (els.dialog.hidden) document.body.style.overflow = "";
  }

  /* ================= filters & chrome visibility ================= */
  function renderFilters() {
    els.filters.innerHTML = FILTERS.map(function (f) {
      return '<button data-filter="' + f + '" aria-pressed="' + (state.filter === f) + '">' + f + "</button>";
    }).join("");
  }

  function renderChrome() {
    var onHome = state.page === "home";
    var onProfile = state.page === "profile";
    els.profilePage.hidden = !onProfile;
    els.storiesWrap.hidden = !onHome;
    // Filters only on home "For You / Following / Explore"
    els.filters.hidden = !(onHome && state.tab === "Feed");
    // Profile tabs drive feed when on profile page
  }

  function renderBottomNav() {
    if (!els.bottomNav) return;
    var onHome = state.page === "home";
    var onProfile = state.page === "profile" && isMe();
    $$("[data-nav]", els.bottomNav).forEach(function (btn) {
      var nav = btn.dataset.nav;
      var active = (nav === "home" && onHome) || (nav === "profile" && onProfile);
      btn.setAttribute("aria-current", active ? "page" : "false");
      btn.classList.toggle("is-active", active);
    });
    // Avatar in bottom nav
    if (els.navAvatar && state.me) {
      els.navAvatar.innerHTML = '<img src="' + esc(av(state.me)) + '" alt="" />';
    } else if (els.navAvatar) {
      els.navAvatar.innerHTML = icon("user", 18);
    }
  }

  /* ================= feed ================= */
  var reqId = 0;

  function buildQuery(offset) {
    var p = [];
    if (state.page === "profile") {
      if (state.tab === "Saved" && isMe()) p.push("filter=saved");
      else if (state.tab === "Liked" && isMe()) p.push("filter=liked");
      else p.push("author=" + encodeURIComponent(state.profile.username));
    } else if (state.tab === "Saved") {
      p.push("filter=saved");
    } else if (state.tab === "Liked") {
      p.push("filter=liked");
    } else if (state.tab === "Media") {
      p.push("author=" + encodeURIComponent((state.profile || state.me).username));
    } else {
      p.push("filter=" + FILTER_KEY[state.filter]);
    }
    if (state.query) p.push("q=" + encodeURIComponent(state.query));
    if (offset) p.push("offset=" + offset);
    return p.join("&");
  }

  function loadPosts(append) {
    if (!state.profile) return;
    var id = ++reqId;
    state.postsError = "";
    if (!append) { state.postsLoading = true; state.posts = []; state.hasMore = false; renderFeed(); }
    return api("/posts?" + buildQuery(append ? state.posts.length : 0)).then(function (d) {
      if (id !== reqId) return;
      state.posts = append ? state.posts.concat(d.results) : d.results;
      state.hasMore = d.hasMore;
      state.postsLoading = false;
      renderFeed();
    }).catch(function (e) {
      if (id !== reqId) return;
      state.postsLoading = false; state.postsError = e.message; renderFeed();
    });
  }

  function setQuery(q) { state.query = q.trim(); loadPosts(); }

  function postHTML(p) {
    var a = p.author;
    return '<article class="post" data-id="' + p.id + '">' +
      '<div class="post__head">' +
        '<a href="#" class="post__avatar profile-link" data-profile="' + esc(a.username) + '" aria-label="Open ' + esc(a.name) + ' profile"><img src="' + esc(av(a)) + '" alt="" loading="lazy" /></a>' +
        '<div class="post__who">' +
          '<div class="post__name"><a href="#" class="profile-link" data-profile="' + esc(a.username) + '"><span>' + esc(a.name) + "</span></a>" +
            (a.verified ? '<i class="verified" style="display:inline-flex">' + icon("check", 15) + "</i>" : "") + "</div>" +
          '<p class="post__sub">@' + esc(a.username) + " · " + esc(ago(p.timestamp)) + (p.location ? " · " + esc(p.location) : "") + "</p>" +
        "</div>" +
        '<div class="menu"><button class="icon-btn" data-act="menu" aria-label="More options" aria-haspopup="true">' + icon("dots", 20) + "</button></div>" +
      "</div>" +
      '<div class="post__media" data-media><img src="' + esc(p.imageUrl) + '" alt="Post by ' + esc(a.name) + '" loading="lazy" /></div>' +
      '<div class="post__body">' +
        '<div class="actions">' +
          '<div class="actions__group">' +
            '<button class="act' + (p.isLiked ? " is-on" : "") + '" data-act="like" aria-label="Like" aria-pressed="' + p.isLiked + '">' + icon("heart", 24) + "</button>" +
            '<button class="act" data-act="comment" aria-label="Comment">' + icon("comment", 23) + "</button>" +
            '<button class="act" data-act="share" aria-label="Share">' + icon("send", 22) + "</button>" +
          "</div>" +
          '<button class="act' + (p.isSaved ? " is-on" : "") + '" data-act="save" aria-label="Save" aria-pressed="' + p.isSaved + '">' + icon("bookmark", 23) + "</button>" +
        "</div>" +
        '<div class="likes" data-likes>' + fmt(p.likesCount) + (p.likesCount === 1 ? " like" : " likes") + "</div>" +
        (p.caption ? '<p class="caption"><b>' + esc(a.username) + "</b> " + esc(p.caption) + "</p>" : "") +
        (p.tags.length ? '<p class="tags">' + p.tags.map(function (t) { return "#" + esc(t); }).join(" ") + "</p>" : "") +
        '<button class="view-comments" data-act="comment"' + (p.comments.length ? "" : " hidden") + " data-view-comments>View all " + p.comments.length + " comments</button>" +
        '<div class="comments" data-comments><div><ul>' + p.comments.map(commentHTML).join("") + "</ul></div></div>" +
        '<div class="composer">' +
          '<img src="' + esc(av(state.me)) + '" alt="" />' +
          '<input type="text" data-draft placeholder="Add a comment..." aria-label="Add a comment" maxlength="500" autocomplete="off" />' +
          '<button data-act="post" disabled>Post</button>' +
        "</div>" +
      "</div>" +
    "</article>";
  }

  function commentHTML(c) {
    return '<li><img src="' + esc(av(c.user)) + '" alt="" loading="lazy" /><div style="min-width:0;flex:1">' +
      "<p><b>" + esc(c.user.username) + "</b> " + esc(c.content) + "</p>" +
      "<small>" + esc(ago(c.timestamp)) + "</small></div></li>";
  }

  function emptyHTML() {
    var msg = state.query ? "No results for “" + esc(state.query) + "”."
      : state.tab === "Saved" ? "Nothing saved yet. Tap the bookmark on a post to keep it here."
      : state.tab === "Liked" ? "No liked posts yet. Tap the heart on a post to see it here."
      : !isMe() ? "No posts yet."
      : state.filter === "Following" ? "No posts here yet. Follow more creators to fill your feed."
      : "No posts yet. Tap + to share the first one.";
    return '<div class="empty">' + msg + "</div>";
  }

  function renderFeed() {
    if (state.postsLoading) { els.feed.className = "feed"; els.feed.innerHTML = '<div class="empty">Loading…</div>'; return; }
    if (state.postsError) {
      els.feed.className = "feed";
      els.feed.innerHTML = '<div class="empty">' + esc(state.postsError) + '<br><button class="more" data-retry>Try again</button></div>';
      return;
    }
    var more = state.hasMore ? '<button class="more" data-more>Load more</button>' : "";

    if (state.tab === "Media") {
      els.feed.className = "grid";
      els.feed.innerHTML = state.posts.length ? state.posts.map(function (p) {
        return '<button data-open-media="' + p.id + '" aria-label="Open post">' +
          '<img src="' + esc(p.imageUrl) + '" alt="" loading="lazy" />' +
          '<span class="grid__likes">' + icon("heart", 12) + " " + fmt(p.likesCount) + "</span></button>";
      }).join("") + more : emptyHTML();
      return;
    }
    els.feed.className = "feed";
    els.feed.innerHTML = state.posts.length ? state.posts.map(postHTML).join("") + more : emptyHTML();
  }

  /* ================= post interactions ================= */
  var articleOf = function (el) { return el.closest(".post"); };

  function paintLike(article, p) {
    var btn = $('[data-act="like"]', article);
    btn.classList.toggle("is-on", p.isLiked);
    btn.setAttribute("aria-pressed", String(p.isLiked));
    $("[data-likes]", article).textContent = fmt(p.likesCount) + (p.likesCount === 1 ? " like" : " likes");
  }

  function toggleLike(id, article) {
    var p = findPost(id);
    if (!p) return;
    p.isLiked = !p.isLiked; p.likesCount += p.isLiked ? 1 : -1;       // optimistic
    paintLike(article, p);
    var btn = $('[data-act="like"]', article);
    btn.classList.remove("pulse"); void btn.offsetWidth; btn.classList.add("pulse");
    api("/posts/" + id + "/like", { method: "POST" }).then(function (r) {
      p.isLiked = r.isLiked; p.likesCount = r.likesCount; paintLike(article, p);
      if (state.tab === "Liked" && !p.isLiked) loadPosts();
    }).catch(function (e) {
      p.isLiked = !p.isLiked; p.likesCount += p.isLiked ? 1 : -1;     // roll back
      paintLike(article, p); toast(e.message);
    });
  }

  function toggleSave(id, article) {
    var p = findPost(id);
    if (!p) return;
    p.isSaved = !p.isSaved;
    var btn = $('[data-act="save"]', article);
    btn.classList.toggle("is-on", p.isSaved); btn.setAttribute("aria-pressed", String(p.isSaved));
    api("/posts/" + id + "/save", { method: "POST" }).then(function (r) {
      p.isSaved = r.isSaved;
      if (state.tab === "Saved" && !p.isSaved) loadPosts();
      else { btn.classList.toggle("is-on", p.isSaved); btn.setAttribute("aria-pressed", String(p.isSaved)); }
    }).catch(function (e) {
      p.isSaved = !p.isSaved;
      btn.classList.toggle("is-on", p.isSaved); btn.setAttribute("aria-pressed", String(p.isSaved));
      toast(e.message);
    });
  }

  function toggleComments(article, force) {
    var box = $("[data-comments]", article);
    var open = typeof force === "boolean" ? force : !box.classList.contains("is-open");
    box.classList.toggle("is-open", open);
    var link = $("[data-view-comments]", article);
    if (link) link.hidden = open || !findPost(article.dataset.id).comments.length;
  }

  function submitComment(article) {
    var input = $("[data-draft]", article);
    var text = input.value.trim();
    var btn = $('[data-act="post"]', article);
    if (!text || btn.disabled) return;
    btn.disabled = true;
    var p = findPost(article.dataset.id);
    api("/posts/" + p.id + "/comments", { method: "POST", body: { content: text } }).then(function (c) {
      p.comments.push(c);
      $("[data-comments] ul", article).insertAdjacentHTML("beforeend", commentHTML(c));
      input.value = "";
      var link = $("[data-view-comments]", article);
      if (link) link.textContent = "View all " + p.comments.length + " comments";
      toggleComments(article, true);
      toast("Comment posted");
    }).catch(function (e) { btn.disabled = false; toast(e.message); });
  }

  var lastTap = { id: null, time: 0 };
  function mediaTap(article) {
    var id = article.dataset.id, now = Date.now();
    if (lastTap.id === id && now - lastTap.time < 300) {
      var p = findPost(id);
      if (p && !p.isLiked) toggleLike(id, article);
      var media = $("[data-media]", article);
      var old = $(".burst", media); if (old) old.remove();
      media.insertAdjacentHTML("beforeend", '<div class="burst">' + icon("heart", 96) + "</div>");
      var burst = $(".burst", media);
      setTimeout(function () { burst.remove(); }, 700);
      lastTap.time = 0;
    } else lastTap = { id: id, time: now };
  }

  function closeMenus() { $$(".menu__list").forEach(function (m) { m.remove(); }); }

  function openMenu(btn) {
    var menu = btn.parentNode, had = $(".menu__list", menu);
    closeMenus();
    if (had) return;
    var article = btn.closest(".post");
    var post = article && findPost(article.dataset.id);
    var items = ["Save", "Copy link", "Report"];
    if (post && state.me && post.author && post.author.id === state.me.id) {
      items.push("Delete");
    }
    var el = document.createElement("div");
    el.className = "menu__list";
    el.innerHTML = items.map(function (a) { return '<button data-menu-item="' + a + '">' + a + "</button>"; }).join("");
    menu.appendChild(el);
  }

  /* ================= dialogs: auth + composer ================= */
  function openDialog(html, dismissible) {
    els.dialog.innerHTML = html;
    els.dialog.dataset.dismissible = dismissible ? "1" : "";
    els.dialog.hidden = false;
    document.body.style.overflow = "hidden";
    var first = $("input, textarea", els.dialog);
    if (first) setTimeout(function () { first.focus(); }, 30);
  }

  function closeDialog() {
    els.dialog.hidden = true; els.dialog.innerHTML = "";
    if (els.viewer.hidden) document.body.style.overflow = "";
  }

  function showAuth(mode) {
    mode = mode || "login";
    var reg = mode === "register";
    openDialog(
      '<div class="viewer__card dialog">' +
        '<div class="dialog__brand"><span class="brand__logo">' + icon("vortex", 20) + '</span><span class="brand__name">Vortex</span></div>' +
        '<div class="tabs" role="tablist">' +
          '<button role="tab" data-auth-tab="login" aria-selected="' + !reg + '">Log in</button>' +
          '<button role="tab" data-auth-tab="register" aria-selected="' + reg + '">Sign up</button></div>' +
        '<form data-form="' + mode + '" novalidate>' +
          (reg ? '<label>Display name<input name="displayName" maxlength="80" autocomplete="name" /></label>' : "") +
          '<label>Username<input name="username" required maxlength="30" autocomplete="username" autocapitalize="none" spellcheck="false" /></label>' +
          '<label>Password<input name="password" type="password" required autocomplete="' + (reg ? "new-password" : "current-password") + '" /></label>' +
          '<p class="form-error" role="alert"></p>' +
          '<button class="btn-primary" type="submit">' + (reg ? "Create account" : "Log in") + "</button>" +
        "</form>" +
      "</div>", false);
  }

  function openComposer() {
    openDialog(
      '<div class="viewer__card dialog">' +
        '<button class="icon-btn dialog__close" data-close-dialog aria-label="Close">' + icon("x", 18) + "</button>" +
        '<h2 class="dialog__title">New post</h2>' +
        '<form data-form="post" novalidate>' +
          '<label class="file-drop">' +
            '<span class="file-drop__hint">' + icon("image", 28) + '<br/>Choose photo from device</span>' +
            '<input name="image" type="file" accept="image/jpeg,image/png,image/gif,image/webp" />' +
            '<img class="file-drop__preview" data-preview hidden alt="Preview" />' +
          "</label>" +
          '<label>Or image URL<input name="imageUrl" type="url" placeholder="https://…" autocomplete="off" /></label>' +
          '<label>Caption<textarea name="caption" maxlength="500" placeholder="Say something…"></textarea></label>' +
          '<label>Location<input name="location" maxlength="80" /></label>' +
          '<label>Tags<input name="tags" placeholder="neon, night, street" /></label>' +
          '<p class="form-error" role="alert"></p>' +
          '<button class="btn-primary" type="submit">Share</button>' +
        "</form>" +
      "</div>", true);
    var form = $("[data-form=post]", els.dialog);
    var fileInput = $("input[name=image]", form);
    var preview = $("[data-preview]", form);
    if (fileInput) fileInput.addEventListener("change", function () { filePreview(fileInput, preview); });
  }

  function openStoryComposer() {
    openDialog(
      '<div class="viewer__card dialog">' +
        '<button class="icon-btn dialog__close" data-close-dialog aria-label="Close">' + icon("x", 18) + "</button>" +
        '<h2 class="dialog__title">New story</h2>' +
        '<form data-form="story" novalidate>' +
          '<label class="file-drop">' +
            '<span class="file-drop__hint">' + icon("camera", 28) + '<br/>Photo (optional)</span>' +
            '<input name="image" type="file" accept="image/jpeg,image/png,image/gif,image/webp" />' +
            '<img class="file-drop__preview" data-preview hidden alt="Preview" />' +
          "</label>" +
          '<label>Or image URL<input name="imageUrl" type="url" placeholder="https://…" autocomplete="off" /></label>' +
          '<label>Text<textarea name="text" maxlength="300" rows="3" placeholder="Write something…"></textarea></label>' +
          '<p class="form-error" role="alert"></p>' +
          '<button class="btn-primary" type="submit">Share to story</button>' +
        "</form>" +
      "</div>", true);
    var form = $("[data-form=story]", els.dialog);
    var fileInput = $("input[name=image]", form);
    var preview = $("[data-preview]", form);
    if (fileInput) fileInput.addEventListener("change", function () { filePreview(fileInput, preview); });
  }

  function openEditProfile() {
    var m = state.me;
    if (!m) return;
    openDialog(
      '<div class="viewer__card dialog">' +
        '<button class="icon-btn dialog__close" data-close-dialog aria-label="Close">' + icon("x", 18) + "</button>" +
        '<h2 class="dialog__title">Edit profile</h2>' +
        '<form data-form="profile" novalidate>' +
          '<div class="edit-avatar">' +
            '<img src="' + esc(av(m)) + '" alt="" data-avatar-preview />' +
            '<label class="btn-follow btn-follow--ghost">' + icon("camera", 14) + " Change photo" +
              '<input name="avatar" type="file" accept="image/jpeg,image/png,image/gif,image/webp" hidden />' +
            "</label>" +
          "</div>" +
          '<label>Display name<input name="displayName" maxlength="80" value="' + esc(m.name || "") + '" /></label>' +
          '<label>Bio<textarea name="bio" maxlength="300" rows="3">' + esc(m.bio || "") + "</textarea></label>" +
          '<label>Location<input name="location" maxlength="80" value="' + esc(m.location || "") + '" /></label>' +
          '<label>Website<input name="website" maxlength="120" value="' + esc(m.website || "") + '" /></label>' +
          '<label>Avatar URL (optional)<input name="avatarUrl" type="url" placeholder="https://…" value="' + esc(m.avatar || "") + '" /></label>' +
          '<label>Cover URL (optional)<input name="coverUrl" type="url" placeholder="https://…" value="' + esc(m.coverImage || "") + '" /></label>' +
          '<p class="form-error" role="alert"></p>' +
          '<button class="btn-primary" type="submit">Save changes</button>' +
        "</form>" +
      "</div>", true);
    var form = $("[data-form=profile]", els.dialog);
    var fileInput = $("input[name=avatar]", form);
    var preview = $("[data-avatar-preview]", form);
    if (fileInput) fileInput.addEventListener("change", function () { filePreview(fileInput, preview); });
  }

  function submitForm(form) {
    var kind = form.dataset.form;
    var data = {};
    $$("input, textarea", form).forEach(function (f) {
      if (f.type === "file") return;
      data[f.name] = f.value;
    });
    var errEl = $(".form-error", form), btn = $('button[type="submit"]', form);
    errEl.textContent = "";
    btn.disabled = true;

    var req;
    if (kind === "login") {
      req = api("/auth/login", { method: "POST", body: { username: data.username, password: data.password }, quiet401: true });
    } else if (kind === "register") {
      req = api("/auth/register", { method: "POST", body: { username: data.username, password: data.password, displayName: data.displayName }, quiet401: true });
    } else if (kind === "post") {
      var fileInput = $("input[name=image]", form);
      var hasFile = fileInput && fileInput.files && fileInput.files[0];
      if (!hasFile && !(data.imageUrl || "").trim()) {
        errEl.textContent = "Choose a photo from your device or enter an image URL.";
        btn.disabled = false;
        return;
      }
      if (hasFile) {
        var fd = new FormData();
        fd.append("image", fileInput.files[0]);
        if (data.caption) fd.append("caption", data.caption);
        if (data.location) fd.append("location", data.location);
        if (data.tags) fd.append("tags", data.tags);
        req = api("/posts", { method: "POST", formData: fd });
      } else {
        req = api("/posts", { method: "POST", body: { imageUrl: data.imageUrl, caption: data.caption, location: data.location, tags: data.tags } });
      }
    } else if (kind === "story") {
      var sFile = $("input[name=image]", form);
      var sHas = sFile && sFile.files && sFile.files[0];
      var sText = (data.text || "").trim();
      if (!sHas && !(data.imageUrl || "").trim() && !sText) {
        errEl.textContent = "Add a photo or write some text.";
        btn.disabled = false;
        return;
      }
      if (sHas) {
        var sfd = new FormData();
        sfd.append("image", sFile.files[0]);
        if (sText) sfd.append("text", sText);
        req = api("/stories", { method: "POST", formData: sfd });
      } else {
        req = api("/stories", { method: "POST", body: { imageUrl: data.imageUrl || "", text: sText } });
      }
    } else if (kind === "profile") {
      var aFile = $("input[name=avatar]", form);
      var aHas = aFile && aFile.files && aFile.files[0];
      if (aHas) {
        var pfd = new FormData();
        pfd.append("avatar", aFile.files[0]);
        pfd.append("displayName", data.displayName || "");
        pfd.append("bio", data.bio || "");
        pfd.append("location", data.location || "");
        pfd.append("website", data.website || "");
        if (data.coverUrl) pfd.append("coverUrl", data.coverUrl);
        req = api("/me", { method: "POST", formData: pfd });
      } else {
        req = api("/me", { method: "POST", body: {
          displayName: data.displayName || "",
          bio: data.bio || "",
          location: data.location || "",
          website: data.website || "",
          avatarUrl: data.avatarUrl || "",
          coverUrl: data.coverUrl || ""
        }});
      }
    } else {
      btn.disabled = false;
      return;
    }

    req.then(function (res) {
      if (kind === "login" || kind === "register") {
        setMe(res); closeDialog(); bootstrap(); toast("Welcome, " + res.name + "!");
      } else if (kind === "post") {
        closeDialog();
        state.posts.unshift(res);
        if (isMe()) { state.profile.postsCount += 1; renderProfile(); }
        if (state.me) state.me.postsCount = (state.me.postsCount || 0) + 1;
        renderFeed();
        toast("Post shared");
      } else if (kind === "story") {
        closeDialog();
        loadStories();
        toast("Story shared – lives for 24h");
      } else if (kind === "profile") {
        setMe(res);
        state.profile = res;
        closeDialog();
        renderProfile();
        renderStories();
        renderBottomNav();
        toast("Profile updated");
      }
    }).catch(function (e) {
      errEl.textContent = e.message;
      btn.disabled = false;
    });
  }

  /* ================= session / boot ================= */
  function setMe(u) { state.me = u; state.profile = u; }

  function logout() {
    api("/auth/logout", { method: "POST" }).catch(function () {}).then(function () {
      state.me = null; state.profile = null; state.posts = []; state.stories = []; state.notifications = []; state.unread = 0;
      state.page = "home";
      renderProfile(); renderStories(); renderNotifications(); renderBottomNav(); els.feed.innerHTML = "";
      showAuth("login");
    });
  }

  function bootstrap() {
    state.page = "home";
    state.tab = "Feed"; state.filter = "For You"; state.query = ""; els.searchInput.value = "";
    state.profile = state.me;
    renderProfile(); renderFilters(); renderChrome(); renderBottomNav();
    loadPosts(); loadStories(); loadNotifications();
  }

  /* ================= events ================= */
  function initEvents() {
    document.addEventListener("click", function (e) {
      var t = e.target;

      if (!t.closest(".menu")) closeMenus();
      if (!els.panel.hidden && !t.closest(".notif")) togglePanel(false);

      var navBtn = t.closest("[data-nav]");
      if (navBtn) {
        e.preventDefault();
        var nav = navBtn.dataset.nav;
        if (nav === "home") goHome();
        else if (nav === "create") { if (state.me) openComposer(); }
        else if (nav === "profile") openProfile("__me");
        return;
      }

      var prof = t.closest("[data-profile]");
      if (prof) {
        e.preventDefault();
        if (!els.viewer.hidden) closeStory();
        openProfile(prof.dataset.profile);
        return;
      }

      var authTab = t.closest("[data-auth-tab]");
      if (authTab) { showAuth(authTab.dataset.authTab); return; }

      if (t.closest("[data-close-dialog]") || (t === els.dialog && els.dialog.dataset.dismissible)) { closeDialog(); return; }

      var tab = t.closest("[data-tab]");
      if (tab) { state.tab = tab.dataset.tab; renderProfile(); renderChrome(); loadPosts(); return; }

      if (t.closest("[data-follow]")) { toggleFollow(); return; }
      if (t.closest("[data-logout]")) { logout(); return; }
      if (t.closest("[data-back-profile]")) { goHome(); return; }
      if (t.closest("[data-edit-profile]")) { openEditProfile(); return; }
      if (t.closest("[data-add-story]")) { openStoryComposer(); return; }

      if (t.closest("[data-close-likers]")) {
        e.stopPropagation();
        var sh = $(".likers-sheet", els.viewer);
        if (sh) sh.remove();
        return;
      }
      var likersBtn = t.closest("[data-story-likers]");
      if (likersBtn) {
        e.stopPropagation();
        showStoryLikers(likersBtn.dataset.storyLikers);
        return;
      }
      var storyLike = t.closest("[data-story-like]");
      if (storyLike) {
        e.stopPropagation();
        // clicking the count area is handled above; heart toggles like
        if (t.closest("[data-story-likes]")) {
          showStoryLikers(storyLike.dataset.storyLike);
          return;
        }
        toggleStoryLike(storyLike.dataset.storyLike);
        return;
      }

      var story = t.closest("[data-story]");
      if (story) { openStory(story.dataset.story); return; }
      if (t.closest("[data-close-story]") || t === els.viewer) { closeStory(); return; }

      var filter = t.closest("[data-filter]");
      if (filter) { state.filter = filter.dataset.filter; renderFilters(); loadPosts(); return; }

      if (t.closest("[data-more]")) { loadPosts(true); return; }
      if (t.closest("[data-retry]")) { loadPosts(); return; }

      var mediaBtn = t.closest("[data-open-media]");
      if (mediaBtn) {
        var pid = mediaBtn.dataset.openMedia;
        state.tab = "Feed";
        renderProfile(); renderChrome();
        // keep this author's posts; scroll to the clicked one
        loadPosts().then(function () {
          var target = $('.post[data-id="' + pid + '"]');
          if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
        });
        return;
      }

      var article = t.closest(".post");
      if (!article) return;

      var item = t.closest("[data-menu-item]");
      if (item) {
        closeMenus();
        if (item.dataset.menuItem === "Save") toggleSave(article.dataset.id, article);
        else if (item.dataset.menuItem === "Copy link") { copyLink(); }
        else if (item.dataset.menuItem === "Delete") {
          if (!confirm("Delete this post?")) return;
          api("/posts/" + article.dataset.id + "/delete", { method: "POST" }).then(function () {
            state.posts = state.posts.filter(function (p) { return String(p.id) !== String(article.dataset.id); });
            if (state.profile) { state.profile.postsCount = Math.max(0, (state.profile.postsCount || 1) - 1); renderProfile(); }
            if (state.me) state.me.postsCount = Math.max(0, (state.me.postsCount || 1) - 1);
            renderFeed();
            toast("Post deleted");
          }).catch(function (e) { toast(e.message); });
        }
        else toast("Thanks – we'll review this post");
        return;
      }

      if (t.closest("[data-media]")) { mediaTap(article); return; }

      var actBtn = t.closest("[data-act]");
      if (!actBtn) return;
      switch (actBtn.dataset.act) {
        case "like": toggleLike(article.dataset.id, article); break;
        case "save": toggleSave(article.dataset.id, article); break;
        case "comment": toggleComments(article); break;
        case "share": copyLink(); break;
        case "menu": openMenu(actBtn); break;
        case "post": submitComment(article); break;
      }
    });

    document.addEventListener("submit", function (e) {
      var form = e.target.closest("[data-form]");
      if (form) { e.preventDefault(); submitForm(form); }
    });

    document.addEventListener("input", function (e) {
      if (e.target.matches("[data-draft]")) {
        $('[data-act="post"]', articleOf(e.target)).disabled = !e.target.value.trim();
      }
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && e.target.matches("[data-draft]")) { e.preventDefault(); submitComment(articleOf(e.target)); }
      if (e.key === "Escape") {
        closeStory(); closeMenus(); togglePanel(false);
        if (els.dialog.dataset.dismissible) closeDialog();
      }
    });

    // refresh notifications every minute while logged in and tab is visible
    setInterval(function () { if (state.me && !document.hidden) loadNotifications(); }, 60000);
  }

  function copyLink() {
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(location.href).catch(function () {});
    toast("Link copied to clipboard");
  }

  /* ================= init ================= */
  initHeader();
  initEvents();
  api("/me", { quiet401: true }).then(function (u) { setMe(u); bootstrap(); }).catch(function () { showAuth("login"); });
})();
