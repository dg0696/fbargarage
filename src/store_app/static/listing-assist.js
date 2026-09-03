(() => {
  const form = document.querySelector("[data-listing-assist]");
  if (!form) return;
  const button = form.querySelector("[data-suggest]");
  const status = form.querySelector("[data-suggest-status]");
  const comps = form.querySelector("[data-comps]");
  if (!button) return;

  const setValue = (name, value) => {
    const field = form.querySelector(`[name="${name}"]`);
    if (field && value != null && value !== "") field.value = value;
  };

  button.addEventListener("click", async () => {
    button.disabled = true;
    if (status) status.textContent = "Looking up eBay matches…";
    const body = new FormData();
    for (const name of ["title", "notes", "description"]) {
      const field = form.querySelector(`[name="${name}"]`);
      if (field) body.append(name, field.value || "");
    }
    const photos = form.querySelector('input[name="photos"]');
    if (photos && photos.files) {
      Array.from(photos.files).forEach((file) => body.append("photos", file));
    }
    try {
      const response = await fetch("/inventory/suggest", { method: "POST", body });
      const payload = await response.json();
      if (!payload.ok) throw new Error(payload.error || "Suggest failed");
      const draft = payload.suggested || {};
      setValue("title", draft.title);
      setValue("description", draft.description);
      setValue("ask_price", draft.ask_price);
      setValue("brand", draft.brand);
      setValue("condition_id", draft.condition_id);
      setValue("ebay_category_id", draft.ebay_category_id);
      setValue("ebay_category_name", draft.ebay_category_name);
      const escape = (value) =>
        String(value || "")
          .replaceAll("&", "&amp;")
          .replaceAll("<", "&lt;")
          .replaceAll(">", "&gt;")
          .replaceAll('"', "&quot;");
      if (comps) {
        const rows = (payload.comps || [])
          .map((row) => {
            const price = row.price ? `$${escape(row.price)}` : "";
            const title = escape(row.title || "listing");
            const href = escape(row.url || "#");
            return `<li><a href="${href}" target="_blank" rel="noreferrer">${title}</a> ${price}</li>`;
          })
          .join("");
        comps.innerHTML = rows
          ? `<p class="muted">Matching eBay listings</p><ul class="comp-list">${rows}</ul>`
          : "<p class=\"muted\">No close eBay matches.</p>";
      }
      const extra = (payload.errors || []).join(" · ");
      if (status) {
        status.textContent = extra
          ? `Filled from ${draft.source || "eBay"}. ${extra}`
          : `Filled from ${draft.source || "eBay"}. Review before saving.`;
      }
    } catch (err) {
      if (status) status.textContent = err.message || "Suggest failed";
    } finally {
      button.disabled = false;
    }
  });
})();
