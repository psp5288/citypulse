/* Shared place search dropdown: debounce, ↑/↓/Enter/Escape, WorldMonitor-style list UX */
(function (global) {
  /**
   * @param {object} opts
   * @param {HTMLInputElement} opts.input
   * @param {HTMLElement} [opts.button]
   * @param {HTMLElement} opts.suggest
   * @param {function(string): Promise<Array<{label:string, lat?:number, lng?:number, lon?:number}>>} opts.fetchRows
   * @param {function(object): void} opts.onPick — row object from fetchRows
   * @param {function(): Promise<void>|void} [opts.onSubmitQuery] — Enter when no highlight (e.g. first result)
   * @param {number} [opts.debounceMs]
   */
  function attach(opts) {
    const input = opts.input;
    const suggest = opts.suggest;
    const debounceMs = opts.debounceMs ?? 220;
    let timer = null;
    /** @type {Array<object>} */
    let rows = [];
    let active = -1;

    if (!input || !suggest) return { detach: () => {} };

    const hide = () => {
      suggest.style.display = "none";
      suggest.innerHTML = "";
      rows = [];
      active = -1;
    };

    const esc = (s) => {
      const d = document.createElement("div");
      d.textContent = s == null ? "" : String(s);
      return d.innerHTML;
    };

    const render = () => {
      if (!rows.length) {
        hide();
        return;
      }
      suggest.innerHTML = rows
        .map(
          (row, idx) =>
            `<button type="button" data-idx="${idx}" class="place-suggest__btn${
              idx === active ? " place-suggest__btn--active" : ""
            }">${esc(row.label)}</button>`
        )
        .join("");
      suggest.style.display = "block";
      suggest.querySelectorAll("button[data-idx]").forEach((el) => {
        el.addEventListener("click", () => {
          const i = Number(el.dataset.idx);
          if (rows[i]) opts.onPick(rows[i]);
        });
      });
    };

    const fetchDebounced = async () => {
      const q = input.value.trim();
      if (!q) {
        hide();
        return;
      }
      try {
        rows = (await opts.fetchRows(q)) || [];
        active = rows.length ? 0 : -1;
        render();
      } catch {
        hide();
      }
    };

    const onInput = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(fetchDebounced, debounceMs);
    };

    const onDocClick = (e) => {
      if (e.target === input || e.target === opts.button || suggest.contains(e.target)) return;
      hide();
    };

    input.addEventListener("input", onInput);
    document.addEventListener("click", onDocClick);
    if (opts.button) opts.button.addEventListener("click", () => opts.onSubmitQuery && opts.onSubmitQuery());

    input.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        hide();
        return;
      }
      if (!rows.length) {
        if (e.key === "Enter" && opts.onSubmitQuery) {
          e.preventDefault();
          opts.onSubmitQuery();
        }
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        active = Math.min(rows.length - 1, active + 1);
        if (active < 0) active = 0;
        render();
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        active = Math.max(0, active - 1);
        render();
        return;
      }
      if (e.key === "Enter") {
        e.preventDefault();
        if (active >= 0 && rows[active]) opts.onPick(rows[active]);
        else if (rows[0]) opts.onPick(rows[0]);
      }
    });

    return {
      detach: () => {
        input.removeEventListener("input", onInput);
        document.removeEventListener("click", onDocClick);
        if (timer) clearTimeout(timer);
        hide();
      },
      hide,
    };
  }

  global.DevCityPlaceSearch = { attach };
})(typeof window !== "undefined" ? window : globalThis);
