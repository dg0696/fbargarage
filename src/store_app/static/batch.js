(() => {
  document.querySelectorAll("[data-batch]").forEach((form) => {
    const boxes = () =>
      document.querySelectorAll(`input[type="checkbox"][form="${form.id}"]:not([data-select-all])`);
    const master = document.querySelector(`[data-select-all][form="${form.id}"]`);
    if (master) {
      master.addEventListener("change", () => {
        boxes().forEach((box) => {
          box.checked = master.checked;
        });
      });
    }
    form.addEventListener("submit", (event) => {
      const selected = Array.from(boxes()).filter((box) => box.checked);
      if (!selected.length) {
        event.preventDefault();
        window.alert("Select at least one row.");
        return;
      }
      const action = form.querySelector("[name='action']");
      const name = action ? action.value : "";
      const labels = {
        remove: "Delete the selected shelf items? eBay listings stay up.",
        end: "End the selected eBay listings now?",
        relist: "Relist the selected ended items on eBay?",
      };
      if (labels[name] && !window.confirm(labels[name])) {
        event.preventDefault();
      }
    });
  });
})();
