document.querySelectorAll("[data-drop]").forEach((zone) => {
  zone.addEventListener("dragover", (event) => event.preventDefault());
  zone.addEventListener("drop", async (event) => {
    event.preventDefault();
    const id = event.dataTransfer.getData("text/plain");
    const version = event.dataTransfer.getData("version");
    const token = document.querySelector('meta[name="csrf"]');
    const note = document.querySelector("#move-note");
    if (!id) {
      return;
    }
    const response = await fetch(`/api/v1/calendar/episodes/${id}`, {
      method: "PATCH",
      headers: {
        "content-type": "application/json",
        "x-csrf-token": token ? token.content : "",
      },
      body: JSON.stringify({ slot_utc: zone.dataset.drop, expected_version: Number(version) }),
    });
    if (!response.ok) {
      const payload = await response.json();
      if (note) {
        note.textContent = payload.detail || "Перенос отклонён. Слот на экране не менялся.";
      }
      return;
    }
    window.location.reload();
  });
});

document.querySelectorAll("[draggable='true']").forEach((row) => {
  row.addEventListener("dragstart", (event) => {
    event.dataTransfer.setData("text/plain", row.dataset.episode || "");
    event.dataTransfer.setData("version", row.dataset.version || "");
  });
});
