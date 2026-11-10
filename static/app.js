"use strict";
// Ajaia Docs frontend: plain JavaScript, no framework.
// Rule: anything that came from the server (titles, names, previews) goes in as TEXT, never as HTML.

const app = document.getElementById("app");
let me = null;          // the signed-in user, or null
let currentTab = "owned";
let leaveEditor = null;   // set by the open editor: stops listeners and saves pending edits
let nextPageMessage = null; // { kind: "error" | "notice", text }: shown once, on whichever page opens next
                            // (a save that failed after the user left, import warnings, "Deleted ...")

// ---------- small helpers ----------

// Build an element. String children become text nodes, so they can never be parsed as HTML.
function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(props)) {
    if (name === "class") node.className = value;
    else if (name.startsWith("on")) node.addEventListener(name.slice(2), value);
    else node.setAttribute(name, value);
  }
  node.append(...children);
  return node;
}

// Call the API. Errors become Error(message) using the server's {"detail": "..."} text.
async function api(path, { method = "GET", body } = {}) {
  const request = { method };
  if (body instanceof FormData) {
    request.body = body; // file upload: the browser sets the multipart header itself
  } else if (body) {
    request.body = JSON.stringify(body);
    request.headers = { "Content-Type": "application/json" };
  }
  let response;
  try {
    response = await fetch("/api" + path, request);
  } catch {
    throw new Error("Could not reach the server");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.detail || "Something went wrong");
    error.status = response.status;
    error.data = data;
    throw error;
  }
  return data;
}

// A visible, accessible message box. Every API error must show up somewhere on screen.
// show() is for errors (coral), info() is for neutral notes (peach).
function makeMessage() {
  const node = el("div", { hidden: "" });
  const labels = { error: "Error", notice: "Note" };
  function display(kind, text) {
    node.className = kind;
    node.setAttribute("role", kind === "error" ? "alert" : "status");
    node.replaceChildren(el("span", { class: "label" }, labels[kind]), text);
    node.hidden = false;
  }
  const message = {
    node,
    show(text) { display("error", text); },
    info(text) { display("notice", text); },
    hide() { node.hidden = true; },
  };
  if (nextPageMessage) {
    display(nextPageMessage.kind, nextPageMessage.text);
    nextPageMessage = null;
  }
  return message;
}

// Put new content on screen and move keyboard/screen-reader focus to its heading.
function mount(...nodes) {
  app.replaceChildren(...nodes);
  const heading = app.querySelector("h1");
  if (heading) { heading.setAttribute("tabindex", "-1"); heading.focus(); }
}

// Timestamps from the server are UTC. SQLite (tests only) omits the zone, so add it.
function formatTime(iso) {
  const hasZone = /(Z|[+-]\d\d:?\d\d)$/.test(iso);
  return new Date(hasZone ? iso : iso + "Z").toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

// A 401 anywhere means the session ended: go back to the sign-in screen.
function handleError(error, message) {
  if (error.status === 401) {
    me = null;
    showLogin("Your session ended. Please sign in again.");
  } else {
    message.show(error.message);
  }
}

// ---------- sign in and sign up ----------

function showLogin(notice) {
  showAuth("login", notice);
}

// One card for both: "login" asks for email and password, "signup" also asks for a username.
function showAuth(mode, notice) {
  const signingUp = mode === "signup";
  const message = makeMessage();
  if (notice) message.show(notice);

  const email = el("input", { id: "email", type: "email", autocomplete: "username", required: "", placeholder: "alice@example.com" });
  const username = el("input", { id: "username", type: "text", autocomplete: "name", required: "", minlength: "2", maxlength: "30", placeholder: "Alice Smith" });
  const password = el("input", {
    id: "password", type: "password", required: "", autocomplete: signingUp ? "new-password" : "current-password",
  });
  if (signingUp) { password.minLength = 8; password.maxLength = 128; }
  const submit = el("button", { class: "btn btn-primary", type: "submit" }, signingUp ? "Create account" : "Sign in");

  const rows = [field("email", "Email", email)];
  if (signingUp) rows.push(field("username", "Display name", username, { hint: "2–30 characters. This is the name other people see." }));
  rows.push(field("password", "Password", password, { hint: signingUp ? "At least 8 characters" : "" }));
  const form = el("form", {}, ...rows, message.node, submit);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    message.hide();
    submit.disabled = true;
    try {
      const body = { email: email.value, password: password.value };
      if (signingUp) body.username = username.value;
      me = await api(signingUp ? "/register" : "/login", { method: "POST", body });
      route(); // signing up also signs you in
    } catch (error) {
      message.show(error.message);
      submit.disabled = false;
    }
  });

  mount(el("div", { class: "login" },
    el("div", { class: "login-card glass" },
      el("span", { class: "label" }, "Ajaia Docs"),
      el("h1", {}, signingUp ? "Create account" : "Sign in"),
      form,
      el("button", {
        class: "link-button", type: "button", onclick: () => showAuth(signingUp ? "login" : "signup"),
      }, signingUp ? "I already have an account" : "Create an account"),
    )));
}

// ---------- shared page pieces ----------

function topBar() {
  const signOut = el("button", { class: "btn", type: "button" }, "Sign out");
  signOut.addEventListener("click", async () => {
    await api("/logout", { method: "POST" }).catch(() => {});
    me = null;
    route();
  });
  return el("header", { class: "topbar" },
    el("span", { class: "label" }, "Ajaia Docs"),
    el("span", { class: "who" }, me.username),
    signOut,
  );
}

function roleBadge(role) {
  return el("span", { class: "badge badge-" + role }, role);
}

// One labelled form row: the label, the input, and an optional hint underneath.
// extraClass is for layout only (the share dialog uses "grow").
function field(id, label, input, { hint = "", extraClass = "" } = {}) {
  const row = el("div", { class: `field ${extraClass}`.trim() }, el("label", { for: id }, label), input);
  if (hint) row.append(el("span", { class: "field-hint" }, hint));
  return row;
}

// The viewer/editor dropdown used by the share dialog (extra props: id, aria-label, onchange).
function accessSelect(props) {
  return el("select", props,
    el("option", { value: "viewer" }, "Can view"), el("option", { value: "editor" }, "Can edit"));
}

// ---------- document list ----------

async function showList() {
  const message = makeMessage();
  const area = el("div", {});
  const create = () => createDocument(message, newButton);
  const newButton = el("button", { class: "btn btn-primary", type: "button", onclick: create }, "New document");

  // Import: the visible button opens the hidden file picker. The server checks type and size.
  const fileInput = el("input", {
    type: "file", accept: ".txt,.md,.docx", hidden: "", "aria-label": "Choose a file to import",
    onchange: () => importFile(fileInput, message, importButton),
  });
  const importButton = el("button", { class: "btn", type: "button", onclick: () => fileInput.click() }, "Import file");

  const tabs = el("div", { class: "tabs glass", role: "tablist" });
  mount(topBar(), el("div", { class: "page" },
    el("div", { class: "page-head" }, el("h1", {}, "Your documents"),
      el("div", { class: "actions" }, importButton, newButton, fileInput)),
    el("p", { class: "hint" }, "Import supports .txt, .md and .docx files up to 2 MB. Images, tables and comments are not imported."),
    el("div", { class: "toolbar" }, tabs),
    message.node,
    area,
  ));
  area.append(el("p", { class: "muted" }, "Loading…"));

  let docs;
  try {
    docs = await api("/documents");
  } catch (error) {
    area.replaceChildren();
    return handleError(error, message);
  }

  function draw() {
    const names = { owned: "Owned by me", shared: "Shared with me" };
    tabs.replaceChildren(...["owned", "shared"].map((key) => {
      return el("button", {
        class: "tab", type: "button", role: "tab", "aria-selected": String(key === currentTab),
        onclick: () => { currentTab = key; draw(); },
      }, `${names[key]} (${docs[key].length})`);
    }));
    area.replaceChildren(docs[currentTab].length ? cardGrid(docs[currentTab]) : emptyState(create));
  }
  draw();
}

function cardGrid(list) {
  return el("div", { class: "grid" }, ...list.map((doc) => {
    const meta = el("div", { class: "meta" }, roleBadge(doc.role));
    if (doc.role !== "owner") meta.append(el("span", {}, "by " + doc.owner));
    if (doc.role === "owner" && doc.share_count > 0) meta.append(el("span", {}, `shared with ${doc.share_count}`));
    meta.append(el("span", {}, formatTime(doc.updated_at)));
    return el("a", { class: "doc-card glass", href: "#/doc/" + doc.id },
      el("h2", {}, doc.title),
      el("p", { class: "preview" }, doc.preview || "Empty document"),
      meta,
    );
  }));
}

function emptyState(create) {
  if (currentTab === "shared") {
    return el("div", { class: "empty glass" }, el("p", {}, "Nothing has been shared with you yet"),
      el("span", { class: "muted" }, "Documents other people share with you will appear here."));
  }
  return el("div", { class: "empty glass" }, el("p", {}, "You have no documents yet"),
    el("button", { class: "btn btn-primary", type: "button", onclick: create }, "Create your first document"));
}

async function createDocument(message, button) {
  message.hide();
  button.disabled = true;
  try {
    const doc = await api("/documents", { method: "POST", body: {} });
    location.hash = "#/doc/" + doc.id;
  } catch (error) {
    handleError(error, message);
    button.disabled = false;
  }
}

async function importFile(input, message, button) {
  const file = input.files[0];
  if (!file) return;
  message.hide();
  button.disabled = true;
  button.textContent = "Importing…";
  const form = new FormData();
  form.append("file", file);
  try {
    const result = await api("/import", { method: "POST", body: form });
    if (result.warnings.length) nextPageMessage = { kind: "notice", text: "Imported with notes: " + result.warnings.join("; ") + "." };
    location.hash = "#/doc/" + result.id; // the new document opens in the editor
  } catch (error) {
    handleError(error, message);
    button.disabled = false;
    button.textContent = "Import file";
  } finally {
    input.value = ""; // so the same file can be picked again
  }
}

// ---------- document page: the editor ----------

const AUTOSAVE_DELAY_MS = 1000;
const POLL_INTERVAL_MS = 10000;
const FORMATS = ["header", "bold", "italic", "underline", "list", "link"]; // link: kept for imported files, no toolbar button

// Quill writes every space as &nbsp;, which never wraps. Turn lone ones back into normal spaces.
// Runs of two or more stay &nbsp; so HTML does not collapse them.
function toStoredHtml(quill) {
  return quill.getSemanticHTML().replace(/(?<!&nbsp;)&nbsp;(?!&nbsp;)/g, " ");
}

function buildToolbar() {
  const button = (name, label, value) => {
    const props = { class: "ql-" + name, type: "button", "aria-label": label };
    if (value) props.value = value;
    return el("button", props);
  };
  return el("div", { class: "editor-toolbar" },
    el("span", { class: "ql-formats" },
      el("select", { class: "ql-header", "aria-label": "Text style" },
        el("option", { value: "1" }), el("option", { value: "2" }), el("option", { value: "3" }), el("option", { selected: "" }))),
    el("span", { class: "ql-formats" },
      button("bold", "Bold"), button("italic", "Italic"), button("underline", "Underline")),
    el("span", { class: "ql-formats" },
      button("list", "Numbered list", "ordered"), button("list", "Bulleted list", "bullet")),
  );
}

async function showDocument(id) {
  const message = makeMessage();
  const holder = el("div", { class: "editor-page" });
  mount(topBar(), el("div", { class: "page" }, el("a", { class: "btn back", href: "#/" }, "← All documents"), message.node, holder));
  let doc;
  try {
    doc = await api("/documents/" + id);
  } catch (error) {
    return handleError(error, message);
  }
  openEditor(doc, holder, message);
}

function openEditor(doc, holder, message) {
  const canEdit = doc.can_edit;
  const titleInput = el("input", { class: "title-input", value: doc.title, maxlength: "200", "aria-label": "Document title" });
  const status = el("span", { class: "status", role: "status" }, el("i"), el("span"));
  const toolbar = canEdit && buildToolbar(); // false for viewers: Quill then shows no toolbar
  const editorBox = el("div", {});
  const who = doc.updated_by ? `Last edited by ${doc.updated_by}, ${formatTime(doc.updated_at)}` : "";

  // The page is the same for everyone. Only the title row and the toolbar differ between editors and viewers.
  const titleRow = el("div", { class: "title-row" }, titleInput);
  const card = el("div", { class: "editor-card glass" });
  if (canEdit) {
    titleRow.append(status);
    // Only the owner can share or delete. The server enforces this too; hiding the buttons is just tidiness.
    if (doc.role === "owner") {
      const currentTitle = () => titleInput.value.trim() || doc.title;
      titleRow.append(
        el("button", { class: "btn", type: "button", onclick: () => openShareDialog(doc.id, currentTitle()) }, "Share"),
        deleteControl(doc.id, currentTitle, message),
      );
    }
    card.append(toolbar);
  } else {
    titleInput.setAttribute("readonly", "");
    titleRow.append(el("span", { class: "badge badge-viewer" }, "View only"));
  }
  card.append(editorBox);
  const banner = el("div", { class: "notice banner", role: "alert", hidden: "" }); // filled in when a newer version appears
  holder.replaceChildren(
    titleRow,
    el("div", { class: "meta" }, roleBadge(doc.role), el("span", {}, `Owner: ${doc.owner}`), el("span", {}, who)),
    banner,
    card,
  );

  const quill = new Quill(editorBox, {
    theme: "snow",
    readOnly: !canEdit,
    placeholder: "Start writing…",
    formats: FORMATS,
    modules: { toolbar },
  });
  // Load the saved HTML. "silent" means this does not count as an edit.
  quill.setContents(quill.clipboard.convert({ html: doc.content }), "silent");
  if (!canEdit) return;
  leaveEditor = startAutosave({ doc, quill, titleInput, status, message, banner });
  quill.focus();
}

// The owner's Delete button. It asks first, and Cancel gets the focus so a stray Enter cannot delete.
function deleteControl(docId, getTitle, message) {
  const box = el("span", { class: "delete-control" });

  function showDeleteButton(focus) {
    const button = el("button", { class: "btn", type: "button", onclick: askToConfirm }, "Delete");
    box.replaceChildren(button);
    if (focus) button.focus();
  }

  function askToConfirm() {
    const cancel = el("button", { class: "btn", type: "button", onclick: () => showDeleteButton(true) }, "Cancel");
    const confirm = el("button", { class: "btn btn-danger", type: "button", onclick: () => remove(confirm) }, "Yes, delete");
    box.replaceChildren(el("span", { class: "delete-question", role: "alert" }, "Delete this document?"), confirm, cancel);
    cancel.focus();
  }

  async function remove(confirmButton) {
    confirmButton.disabled = true;
    const title = getTitle();
    try {
      await api("/documents/" + docId, { method: "DELETE" });
    } catch (error) {
      showDeleteButton(true);
      return handleError(error, message);
    }
    leaveEditor({ discard: true }); // the document is gone: do not try to save into it
    leaveEditor = null;
    nextPageMessage = { kind: "notice", text: `Deleted “${title}”.` };
    location.hash = "#/";
  }

  box.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && box.querySelector(".btn-danger")) showDeleteButton(true);
  });
  showDeleteButton(false);
  return box;
}

// Saving for an editable document: autosave, Ctrl+S, and change detection (SPEC section 7).
// Returns the function that route() calls when the user leaves the page.
function startAutosave({ doc, quill, titleInput, status, message, banner }) {
  let baseHash = doc.content_hash;  // hash of the version we loaded or last saved (SPEC section 7)
  let contentDirty = false;         // content changed since the last save
  let titleDirty = false;
  let saving = false;               // a request is in flight
  let conflictHash = null;          // set while the banner is up: the hash of the newer version someone saved. Autosave pauses.
  let active = true;                // false once the user leaves this page
  let discarded = false;            // true if the document was deleted: nothing to save, no errors to report
  let timer = null;

  function hasUnsavedChanges() { return contentDirty || titleDirty; }

  function setStatus(state, text) {
    status.dataset.state = state;
    status.lastChild.textContent = text;
  }
  setStatus("saved", "All changes saved");

  function scheduleSave() {
    clearTimeout(timer);
    timer = setTimeout(save, AUTOSAVE_DELAY_MS);
  }

  // Called after any edit: show "Unsaved changes" and save once the user pauses.
  function edited() {
    setStatus("pending", "Unsaved changes");
    scheduleSave();
  }

  async function save() {
    clearTimeout(timer);
    if (conflictHash || saving || !hasUnsavedChanges()) return;

    const body = {};
    const title = titleInput.value.trim();
    const sendTitle = titleDirty && title !== "";
    const sendContent = contentDirty;
    if (titleDirty && title === "") setStatus("error", "Title can't be empty");
    if (!sendTitle && !sendContent) return;
    if (sendTitle) { body.title = title; titleDirty = false; }
    if (sendContent) { body.content = toStoredHtml(quill); body.base_hash = baseHash; contentDirty = false; }

    saving = true;
    if (active) { message.hide(); setStatus("saving", "Saving…"); }
    try {
      const saved = await api("/documents/" + doc.id, { method: "PATCH", body });
      // Only a content save may move baseHash. A title-only save must not hide someone else's newer content.
      if (sendContent) baseHash = saved.content_hash;
      if (active) {
        if (hasUnsavedChanges()) setStatus("pending", "Unsaved changes");
        else setStatus("saved", "Saved " + new Date().toLocaleTimeString([], { timeStyle: "short" }));
      }
    } catch (error) {
      if (sendTitle) titleDirty = true;   // nothing was saved: keep the flags so Ctrl+S can retry
      if (sendContent) contentDirty = true;
      if (!active) {
        if (!discarded) nextPageMessage = { kind: "error", text: `Changes to "${titleInput.value}" were not saved. ${error.message}` };
      } else if (error.status === 409) {
        // Someone saved first. The 409 response carries their version's details.
        const theirs = error.data.current;
        showConflict({ by: theirs.updated_by, at: theirs.updated_at, hash: theirs.content_hash });
      } else {
        setStatus("error", "Not saved");
        message.show(`Could not save: ${error.message}. Your changes are still on this page. Press Ctrl+S to try again.`);
      }
    } finally {
      saving = false;
      if (active && hasUnsavedChanges() && !conflictHash && status.dataset.state !== "error") scheduleSave();
    }
  }

  // ----- someone else saved a newer version: the banner and its three choices -----

  function showConflict({ by, at, hash }) {
    conflictHash = hash;
    clearTimeout(timer);
    setStatus("error", "Newer version exists");
    banner.replaceChildren(
      el("span", { class: "label" }, "Newer version"),
      el("span", { class: "banner-text" },
        `${by || "Someone"} edited this document at ${formatTime(at)}. Autosave is paused until you choose.`),
      el("div", { class: "banner-actions" },
        el("button", { class: "btn btn-primary", type: "button", onclick: loadTheirVersion }, "Load their version"),
        el("button", { class: "btn", type: "button", onclick: keepMine }, "Keep mine and overwrite"),
        el("button", { class: "btn", type: "button", onclick: downloadMine }, "Download my copy")),
    );
    banner.hidden = false;
  }

  function closeConflict() {
    conflictHash = null;
    banner.hidden = true;
  }

  // Replace the editor with what is saved on the server. Edits made here since the last save are discarded.
  async function loadTheirVersion() {
    try {
      const latest = await api("/documents/" + doc.id);
      quill.setContents(quill.clipboard.convert({ html: latest.content }), "silent");
      quill.history.clear(); // Undo must not jump back into the old text
      baseHash = latest.content_hash;
      contentDirty = false;
      closeConflict();
      message.hide();
      if (titleDirty) edited();
      else setStatus("saved", "Loaded their version");
    } catch (error) {
      message.show(error.message);
    }
  }

  // Build on their version's hash and save our text over it.
  function keepMine() {
    baseHash = conflictHash;
    contentDirty = true;
    closeConflict();
    save();
  }

  function downloadMine() {
    const title = titleInput.value.trim() || "document";
    // el() escapes the title text, so a title such as "A & <B>" cannot break the file's HTML.
    const page = `<!doctype html>\n<meta charset="utf-8">\n${el("title", {}, title).outerHTML}\n${toStoredHtml(quill)}\n`;
    const url = URL.createObjectURL(new Blob([page], { type: "text/html" }));
    el("a", { href: url, download: title + ".html" }).click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  // Every 10 seconds, ask the server whether the saved version still matches the one we started from.
  async function checkForNewerVersion() {
    if (document.hidden || saving || conflictHash) return; // nobody is looking at a background tab
    const hashWhenAsked = baseHash;
    try {
      const meta = await api(`/documents/${doc.id}/meta`);
      // Ignore the answer if one of our own saves finished meanwhile: it describes the version before our save.
      if (saving || conflictHash || baseHash !== hashWhenAsked) return;
      if (meta.content_hash !== baseHash) showConflict({ by: meta.updated_by, at: meta.updated_at, hash: meta.content_hash });
    } catch (error) {
      if (error.status === 401 || error.status === 404) {
        // The session ended, or the document was deleted or unshared: asking again can never work.
        // Show it here (not on the sign-in screen) so the text being edited stays on the page.
        clearInterval(poller);
        message.show(error.message);
      }
      // Any other failure is a missed check, which is harmless: the next save reports a real problem.
    }
  }
  const poller = setInterval(checkForNewerVersion, POLL_INTERVAL_MS);

  quill.on("text-change", (_delta, _old, source) => {
    if (source !== "user") return;
    contentDirty = true;
    edited();
  });
  titleInput.addEventListener("input", () => {
    titleDirty = true;
    edited();
  });

  function onKeydown(event) {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      save();
    }
  }
  function warnBeforeClosing(event) {
    if (hasUnsavedChanges() || saving) { event.preventDefault(); event.returnValue = ""; }
  }
  document.addEventListener("keydown", onKeydown);
  window.addEventListener("beforeunload", warnBeforeClosing);

  // route() calls this when the user leaves the page: stop listening and save whatever is pending.
  // With { discard: true } (the document was just deleted) nothing is saved.
  return function leave({ discard = false } = {}) {
    active = false;
    discarded = discard;
    clearInterval(poller);
    document.removeEventListener("keydown", onKeydown);
    window.removeEventListener("beforeunload", warnBeforeClosing);
    if (discard) { clearTimeout(timer); return; }
    if (conflictHash && hasUnsavedChanges()) {
      nextPageMessage = { kind: "error", text: `Changes to "${titleInput.value}" were not saved because someone else saved a newer version.` };
    }
    save();
  };
}

// ---------- share dialog (owner only) ----------

function openShareDialog(docId, title) {
  const message = makeMessage();
  const email = el("input", { id: "share-email", type: "email", required: "", autocomplete: "off", placeholder: "bob@example.com" });
  const role = accessSelect({ id: "share-role" });
  const addButton = el("button", { class: "btn btn-primary", type: "submit" }, "Share");
  const done = el("button", { class: "btn", type: "button", onclick: () => dialog.close() }, "Done");
  const people = el("ul", { class: "people" });
  const form = el("form", { class: "share-form" },
    field("share-email", "Email", email, { extraClass: "grow" }),
    field("share-role", "Access", role),
    addButton,
  );
  const dialog = el("dialog", { class: "dialog glass", "aria-labelledby": "share-title" },
    el("h2", { id: "share-title" }, `Share “${title}”`),
    form, message.node, people,
    el("div", { class: "dialog-actions" }, done),
  );

  const sharesUrl = `/documents/${docId}/shares`;

  function fail(error) {
    if (error.status === 401) { dialog.close(); handleError(error); } // session ended: back to sign-in
    else message.show(error.message);
  }

  function draw(list) {
    if (!list.length) { people.replaceChildren(el("li", { class: "muted" }, "Not shared with anyone yet.")); return; }
    people.replaceChildren(...list.map((person) => {
      const access = accessSelect({
        "aria-label": `Access for ${person.email}`,
        onchange: () => change(() => api(sharesUrl, { method: "PUT", body: { email: person.email, role: access.value } })),
      });
      access.value = person.role;
      const remove = el("button", {
        class: "btn", type: "button", "aria-label": `Remove access for ${person.email}`,
        onclick: () => change(() => api(`${sharesUrl}/${encodeURIComponent(person.email)}`, { method: "DELETE" })),
      }, "Remove");
      return el("li", { class: "person" },
        el("span", { class: "person-info" }, el("b", {}, person.username), el("span", { class: "muted" }, person.email)),
        access, remove);
    }));
  }

  async function reload() {
    try { draw(await api(sharesUrl)); } catch (error) { fail(error); }
  }

  // Run one change, then always reload the list so the screen matches the server (also undoes a refused change).
  async function change(action) {
    message.hide();
    let ok = true;
    try { await action(); } catch (error) { ok = false; fail(error); }
    await reload();
    return ok;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    addButton.disabled = true;
    const ok = await change(() => api(sharesUrl, { method: "PUT", body: { email: email.value, role: role.value } }));
    addButton.disabled = false;
    if (ok) { email.value = ""; email.focus(); }
  });
  dialog.addEventListener("close", () => dialog.remove()); // Done and Escape both close it

  document.body.append(dialog);
  dialog.showModal();
  reload();
}

// ---------- routing ----------

function route() {
  document.querySelectorAll("dialog[open]").forEach((dialog) => dialog.close());
  if (leaveEditor) { leaveEditor(); leaveEditor = null; }
  if (!me) return showLogin();
  const match = location.hash.match(/^#\/doc\/(\d+)$/);
  if (match) showDocument(match[1]);
  else showList();
}

window.addEventListener("hashchange", route);
api("/me").then((user) => { me = user; }).catch(() => { me = null; }).finally(route);
