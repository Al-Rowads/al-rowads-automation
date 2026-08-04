"use strict";

const state = {
  page: 1,
  pageSize: 100,
  status: "all",
  search: "",
  pages: 1,
  savedMessage: "",
  messageDirty: false,
  preview: null,
  previewFile: null,
  loading: false,
};

const elements = {
  messageInput: document.querySelector("#message-input"),
  messageCount: document.querySelector("#message-count"),
  messageState: document.querySelector("#message-state"),
  saveMessage: document.querySelector("#save-message"),
  numbersFile: document.querySelector("#numbers-file"),
  fileName: document.querySelector("#file-name"),
  previewButton: document.querySelector("#preview-import"),
  previewBox: document.querySelector("#import-preview"),
  previewSummary: document.querySelector("#preview-summary"),
  issueList: document.querySelector("#issue-list"),
  commitButton: document.querySelector("#commit-import"),
  contactsBody: document.querySelector("#contacts-body"),
  tableWrap: document.querySelector("#contacts-table-wrap"),
  listStatus: document.querySelector("#list-status"),
  totalCount: document.querySelector("#total-count"),
  pendingCount: document.querySelector("#pending-count"),
  completedCount: document.querySelector("#completed-count"),
  resultCount: document.querySelector("#result-count"),
  searchInput: document.querySelector("#search-input"),
  filters: document.querySelector("#status-filters"),
  previousPage: document.querySelector("#previous-page"),
  nextPage: document.querySelector("#next-page"),
  pageLabel: document.querySelector("#page-label"),
  refreshButton: document.querySelector("#refresh-button"),
  toast: document.querySelector("#toast"),
};

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  let payload = {};
  try {
    payload = await response.json();
  } catch (_error) {
    payload = { message: "حدث خطأ غير متوقع من الخادم." };
  }
  if (!response.ok) {
    const error = new Error(payload.message || "تعذّر إكمال الطلب.");
    error.code = payload.error;
    error.status = response.status;
    throw error;
  }
  return payload;
}

function showToast(message, kind = "success") {
  elements.toast.textContent = message;
  elements.toast.className = `toast ${kind}`;
  elements.toast.hidden = false;
  window.clearTimeout(showToast.timeout);
  showToast.timeout = window.setTimeout(() => {
    elements.toast.hidden = true;
  }, 4200);
}

function setBusy(button, busy, busyText) {
  if (busy) {
    button.dataset.originalText = button.textContent;
    button.textContent = busyText;
  } else if (button.dataset.originalText) {
    button.textContent = button.dataset.originalText;
  }
  button.disabled = busy;
}

async function loadContacts({ quiet = false } = {}) {
  if (state.loading) return;
  state.loading = true;
  if (!quiet) {
    elements.listStatus.textContent = "جارٍ تحميل الأرقام…";
    elements.tableWrap.classList.add("loading");
  }

  const query = new URLSearchParams({
    page: String(state.page),
    page_size: String(state.pageSize),
    status: state.status,
  });
  if (state.search) query.set("q", state.search);

  try {
    const payload = await requestJson(`/api/contacts?${query}`);
    const calculatedPages = Math.max(1, Math.ceil(payload.filtered_total / payload.page_size));
    if (state.page > calculatedPages) {
      state.page = calculatedPages;
      state.loading = false;
      return loadContacts({ quiet });
    }
    state.pages = calculatedPages;
    renderContacts(payload.contacts);
    renderCounts(payload);

    if (!state.messageDirty) {
      state.savedMessage = payload.workspace.message;
      elements.messageInput.value = state.savedMessage;
      updateMessageCount();
      elements.messageState.textContent = state.savedMessage ? "محفوظة" : "لم تُحفظ رسالة بعد";
    }
    elements.listStatus.textContent = payload.contacts.length ? "" : emptyStateText(payload.counts.total);
  } catch (error) {
    elements.listStatus.textContent = error.message;
    showToast(error.message, "error");
  } finally {
    state.loading = false;
    elements.tableWrap.classList.remove("loading");
  }
}

function emptyStateText(total) {
  if (total === 0) return "لا توجد أرقام بعد. استورد ملف TXT للبدء.";
  return "لا توجد أرقام تطابق البحث أو عامل التصفية.";
}

function renderContacts(contacts) {
  elements.contactsBody.replaceChildren();
  const fragment = document.createDocumentFragment();

  for (const contact of contacts) {
    const row = document.createElement("tr");
    if (contact.completed) row.classList.add("is-completed");

    const statusCell = document.createElement("td");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "contact-checkbox";
    checkbox.checked = contact.completed;
    checkbox.setAttribute("aria-label", `تغيير حالة الرقم ${contact.phone}`);
    checkbox.addEventListener("change", () => handleContactToggle(contact, checkbox, row));
    statusCell.append(checkbox);

    const phoneCell = document.createElement("td");
    phoneCell.className = "phone-number";
    phoneCell.dir = "ltr";
    phoneCell.textContent = contact.phone;

    const positionCell = document.createElement("td");
    positionCell.className = "position";
    positionCell.textContent = new Intl.NumberFormat("ar").format(contact.position);

    row.append(statusCell, phoneCell, positionCell);
    fragment.append(row);
  }
  elements.contactsBody.append(fragment);
}

async function handleContactToggle(contact, checkbox, row) {
  if (checkbox.checked) {
    if (!state.savedMessage) {
      checkbox.checked = false;
      elements.messageInput.focus();
      showToast("احفظ نص الرسالة أولاً.", "error");
      return;
    }

    checkbox.disabled = true;
    row.classList.add("is-completed");
    const form = document.createElement("form");
    form.method = "post";
    form.action = `/contacts/${contact.id}/open`;
    form.target = "_blank";
    form.hidden = true;
    document.body.append(form);
    form.requestSubmit();
    form.remove();
    window.setTimeout(() => {
      checkbox.disabled = false;
      loadContacts({ quiet: true });
    }, 1200);
    return;
  }

  checkbox.disabled = true;
  try {
    await requestJson(`/api/contacts/${contact.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ completed: false }),
    });
    row.classList.remove("is-completed");
    await loadContacts({ quiet: true });
  } catch (error) {
    checkbox.checked = true;
    showToast(error.message, "error");
  } finally {
    checkbox.disabled = false;
  }
}

function renderCounts(payload) {
  const numberFormat = new Intl.NumberFormat("ar");
  elements.totalCount.textContent = numberFormat.format(payload.counts.total);
  elements.pendingCount.textContent = numberFormat.format(payload.counts.pending);
  elements.completedCount.textContent = numberFormat.format(payload.counts.completed);
  elements.resultCount.textContent = `${numberFormat.format(payload.filtered_total)} نتيجة`;
  elements.pageLabel.textContent = `الصفحة ${numberFormat.format(state.page)} من ${numberFormat.format(state.pages)}`;
  elements.previousPage.disabled = state.page <= 1;
  elements.nextPage.disabled = state.page >= state.pages;
}

function updateMessageCount() {
  elements.messageCount.textContent = `${elements.messageInput.value.length} / 2000`;
}

async function saveMessage() {
  const message = elements.messageInput.value.trim();
  if (!message) {
    showToast("اكتب نص الرسالة قبل الحفظ.", "error");
    elements.messageInput.focus();
    return;
  }
  setBusy(elements.saveMessage, true, "جارٍ الحفظ…");
  try {
    const payload = await requestJson("/api/message", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    state.savedMessage = payload.message;
    state.messageDirty = false;
    elements.messageInput.value = payload.message;
    elements.messageState.textContent = "محفوظة";
    showToast("تم حفظ الرسالة لكل الأجهزة.");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    setBusy(elements.saveMessage, false);
  }
}

async function previewImport() {
  const file = elements.numbersFile.files[0];
  if (!file) {
    showToast("اختر ملف TXT أولاً.", "error");
    return;
  }
  setBusy(elements.previewButton, true, "جارٍ الفحص…");
  const formData = new FormData();
  formData.append("file", file);
  try {
    const payload = await requestJson("/api/imports/preview", {
      method: "POST",
      body: formData,
    });
    state.preview = payload;
    state.previewFile = file;
    renderPreview(payload);
  } catch (error) {
    state.preview = null;
    state.previewFile = null;
    elements.previewBox.hidden = true;
    showToast(error.message, "error");
  } finally {
    setBusy(elements.previewButton, false);
  }
}

function renderPreview(preview) {
  const numberFormat = new Intl.NumberFormat("ar");
  elements.previewSummary.replaceChildren(
    summaryChip("أرقام صالحة", preview.valid_count, "valid"),
    summaryChip("أسطر غير صالحة", preview.invalid_count, "invalid"),
    summaryChip("أرقام مكررة", preview.duplicate_count, "duplicate"),
    summaryChip("أسطر فارغة", preview.blank_count, "blank"),
  );
  elements.issueList.replaceChildren();
  if (preview.issues.length) {
    const title = document.createElement("p");
    title.className = "issue-title";
    title.textContent = "الأسطر التي لن تُستورد:";
    elements.issueList.append(title);
    const list = document.createElement("ul");
    for (const issue of preview.issues) {
      const item = document.createElement("li");
      const reason = issue.reason === "duplicate" ? "مكرر" : "صيغة غير صالحة";
      item.textContent = `السطر ${numberFormat.format(issue.line)}: ${issue.value} — ${reason}`;
      list.append(item);
    }
    elements.issueList.append(list);
    if (preview.issues_truncated) {
      const note = document.createElement("p");
      note.textContent = "تُعرض أول 200 ملاحظة فقط.";
      elements.issueList.append(note);
    }
  }
  elements.previewBox.hidden = false;
}

function summaryChip(label, value, className) {
  const chip = document.createElement("div");
  chip.className = `summary-chip ${className}`;
  const strong = document.createElement("strong");
  strong.textContent = new Intl.NumberFormat("ar").format(value);
  const span = document.createElement("span");
  span.textContent = label;
  chip.append(strong, span);
  return chip;
}

async function commitImport() {
  if (!state.preview || !state.previewFile) return;
  setBusy(elements.commitButton, true, "جارٍ الاستبدال…");
  const formData = new FormData();
  formData.append("file", state.previewFile);
  formData.append("digest", state.preview.digest);
  formData.append("list_revision", String(state.preview.list_revision));
  try {
    const payload = await requestJson("/api/imports/commit", {
      method: "POST",
      body: formData,
    });
    showToast(`تم استيراد ${new Intl.NumberFormat("ar").format(payload.imported_count)} رقم.`);
    state.preview = null;
    state.previewFile = null;
    state.page = 1;
    elements.previewBox.hidden = true;
    elements.numbersFile.value = "";
    elements.fileName.textContent = "اختر ملف numbers.txt";
    await loadContacts();
  } catch (error) {
    if (error.code === "stale_import") {
      state.preview = null;
      state.previewFile = null;
      elements.previewBox.hidden = true;
    }
    showToast(error.message, "error");
  } finally {
    setBusy(elements.commitButton, false);
  }
}

let searchTimer;
elements.searchInput.addEventListener("input", () => {
  window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(() => {
    state.search = elements.searchInput.value.trim().replace(/^\+/, "");
    state.page = 1;
    loadContacts();
  }, 300);
});

elements.messageInput.addEventListener("input", () => {
  state.messageDirty = elements.messageInput.value !== state.savedMessage;
  elements.messageState.textContent = state.messageDirty ? "تغييرات غير محفوظة" : "محفوظة";
  updateMessageCount();
});
elements.saveMessage.addEventListener("click", saveMessage);
elements.numbersFile.addEventListener("change", () => {
  const file = elements.numbersFile.files[0];
  elements.fileName.textContent = file ? file.name : "اختر ملف numbers.txt";
  state.preview = null;
  state.previewFile = null;
  elements.previewBox.hidden = true;
});
elements.previewButton.addEventListener("click", previewImport);
elements.commitButton.addEventListener("click", commitImport);
elements.filters.addEventListener("click", (event) => {
  const button = event.target.closest("[data-status]");
  if (!button) return;
  state.status = button.dataset.status;
  state.page = 1;
  for (const filter of elements.filters.querySelectorAll(".filter")) {
    filter.classList.toggle("active", filter === button);
  }
  loadContacts();
});
elements.previousPage.addEventListener("click", () => {
  if (state.page > 1) {
    state.page -= 1;
    loadContacts();
  }
});
elements.nextPage.addEventListener("click", () => {
  if (state.page < state.pages) {
    state.page += 1;
    loadContacts();
  }
});
elements.refreshButton.addEventListener("click", () => loadContacts());
window.addEventListener("focus", () => loadContacts({ quiet: true }));

updateMessageCount();
loadContacts();

