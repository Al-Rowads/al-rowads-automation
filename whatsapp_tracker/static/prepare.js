"use strict";

const card = document.querySelector("#prepare-card");
const copyAndOpen = document.querySelector("#copy-and-open");
const status = document.querySelector("#prepare-status");
const fallback = document.querySelector("#prepare-fallback");
const openForm = document.querySelector("#open-whatsapp-form");

let photoBlob = null;

function showFallback(message, { allowRetry = false } = {}) {
  status.textContent = message;
  status.classList.add("error-text");
  copyAndOpen.hidden = !allowRetry;
  copyAndOpen.disabled = !allowRetry;
  fallback.hidden = false;
}

async function preparePhoto() {
  const photoUrl = card.dataset.photoUrl;
  if (!photoUrl) return;

  if (!window.isSecureContext || !navigator.clipboard?.write || !("ClipboardItem" in window)) {
    showFallback("هذا المتصفح لا يدعم نسخ الصور. استخدم التنزيل والإرفاق اليدوي.");
    return;
  }

  try {
    const response = await fetch(photoUrl, { credentials: "same-origin" });
    if (!response.ok) throw new Error("photo_load_failed");
    photoBlob = await response.blob();
    if (photoBlob.type !== "image/png") throw new Error("invalid_photo_type");
    status.textContent = "الصورة جاهزة. اضغط الزر ثم الصقها داخل واتساب.";
    copyAndOpen.disabled = false;
  } catch (_error) {
    showFallback("تعذّر تجهيز الصورة للنسخ. جرّب تنزيلها وإرفاقها يدوياً.");
  }
}

copyAndOpen.addEventListener("click", async () => {
  if (!photoBlob) {
    showFallback("الصورة غير جاهزة للنسخ. استخدم التنزيل والإرفاق اليدوي.");
    return;
  }

  copyAndOpen.disabled = true;
  copyAndOpen.textContent = "جارٍ النسخ…";
  try {
    await navigator.clipboard.write([
      new ClipboardItem({ "image/png": photoBlob }),
    ]);
    status.textContent = "تم نسخ الصورة. جارٍ فتح واتساب…";
    openForm.requestSubmit();
  } catch (_error) {
    copyAndOpen.textContent = "إعادة محاولة النسخ وفتح واتساب";
    showFallback(
      "لم يسمح المتصفح بنسخ الصورة. نزّلها ثم افتح واتساب.",
      { allowRetry: true },
    );
  }
});

preparePhoto();
