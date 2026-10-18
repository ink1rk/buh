(() => {
  const nav = document.querySelector(".nav");
  const toggle = document.querySelector(".nav-toggle");
  const menu = document.querySelector(".menu");
  const path = location.pathname.split("/").pop() || "index.html";

  document.querySelectorAll(".menu a").forEach((link) => {
    const href = link.getAttribute("href") || "";
    const file = href.split("/").pop();
    if (file === path || (path === "" && file === "index.html")) {
      link.setAttribute("aria-current", "page");
    }
  });

  const dock = document.querySelector(".dock");
  const onScroll = () => {
    nav?.classList.toggle("is-stuck", window.scrollY > 8);
    if (dock?.classList.contains("dock-defer")) {
      dock.classList.toggle("is-visible", window.scrollY > 160);
    }
  };
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  const closeMenu = () => {
    menu?.classList.remove("open");
    toggle?.setAttribute("aria-expanded", "false");
    if (toggle) toggle.textContent = "Меню";
  };
  toggle?.addEventListener("click", () => {
    const open = menu.classList.toggle("open");
    toggle.setAttribute("aria-expanded", String(open));
    toggle.textContent = open ? "Закрыть" : "Меню";
  });
  menu?.querySelectorAll("a").forEach((link) => link.addEventListener("click", closeMenu));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeMenu();
  });

  const toast = document.querySelector(".toast");
  let toastTimer = 0;
  const showToast = (text) => {
    if (!toast) return;
    toast.textContent = text;
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), 2200);
  };

  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      const id = button.getAttribute("data-copy");
      const node = id ? document.getElementById(id) : null;
      const text = node ? node.innerText.trim() : button.getAttribute("data-copy-text") || "";
      try {
        await navigator.clipboard.writeText(text);
        showToast("Скопировано");
      } catch {
        showToast("Не удалось скопировать");
      }
    });
  });

  const form = document.querySelector("[data-request-form]");
  const list = document.querySelector("[data-request-list]");
  const key = "landishi-requests";
  const read = () => {
    try {
      return JSON.parse(localStorage.getItem(key) || "[]");
    } catch {
      return [];
    }
  };
  const write = (items) => localStorage.setItem(key, JSON.stringify(items));

  const render = () => {
    if (!list) return;
    const items = read();
    if (!items.length) {
      list.innerHTML = "<p>Пока пусто. Заявки с этого телефона или компьютера появятся здесь.</p>";
      return;
    }
    list.innerHTML = items
      .map(
        (item) => `<article>
          <h3>${escapeHtml(item.topic)}</h3>
          <p>${escapeHtml(item.name)} · пом. ${escapeHtml(item.place)} · ${escapeHtml(item.phone)}</p>
          <p>${escapeHtml(item.message)}</p>
          <p>${escapeHtml(item.created)} · номер ${escapeHtml(item.id)}</p>
        </article>`
      )
      .join("");
  };

  const escapeHtml = (value) =>
    String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");

  render();

  form?.addEventListener("submit", (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const name = String(data.get("name") || "").trim();
    const phone = String(data.get("phone") || "").trim();
    const place = String(data.get("place") || "").trim();
    const topic = String(data.get("topic") || "").trim();
    const message = String(data.get("message") || "").trim();
    const digits = phone.replace(/\D/g, "");
    const error = form.querySelector(".error");
    if (name.length < 2 || digits.length < 10 || place.length < 1 || message.length < 8) {
      if (error) error.hidden = false;
      return;
    }
    if (error) error.hidden = true;
    const items = read();
    const id = `ЛД-${String(Date.now()).slice(-6)}`;
    items.unshift({
      id,
      name,
      phone,
      place,
      topic,
      message,
      created: new Date().toLocaleString("ru-RU", { dateStyle: "long", timeStyle: "short" }),
    });
    write(items.slice(0, 20));
    form.hidden = true;
    const receipt = document.querySelector("[data-receipt]");
    if (receipt) {
      receipt.hidden = false;
      const number = receipt.querySelector("[data-receipt-id]");
      if (number) number.textContent = id;
    }
    render();
  });

  document.querySelector("[data-clear-requests]")?.addEventListener("click", () => {
    localStorage.removeItem(key);
    render();
    showToast("Список на этом устройстве очищен");
  });
})();
