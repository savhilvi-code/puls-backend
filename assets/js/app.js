const N8N_WEBHOOK_URL = "https://puls-backend-t3sn.onrender.com/chat";
const SPLINE_SCENE_URL = "";

    const iconMap = {
      bot: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="5" y="8" width="14" height="10" rx="3"/><path d="M12 4v4M8 13h.01M16 13h.01M7 21h10M3 11v4M21 11v4"/></svg>',
      home: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/></svg>',
      journal: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 7h6M9 11h6M9 15h4"/></svg>',
      history: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v6h6"/><path d="M12 7v5l3 2"/></svg>',
      car: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 13l2-5h12l2 5"/><rect x="3" y="13" width="18" height="6" rx="2"/><path d="M7 19v2M17 19v2M7 16h.01M17 16h.01"/></svg>',
      service: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14 7l3-3 3 3-3 3zM4 20l6-6M6 4l14 14M4 10l6-6"/></svg>',
      file: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6M8 13h8M8 17h6"/></svg>',
      play: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M10 8l6 4-6 4z"/></svg>',
      settings: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2 3-.2-.1a1.7 1.7 0 0 0-2 .2 1.7 1.7 0 0 0-.8 1.5V22h-3.6v-.3a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.9.3l-.2.1-2-3 .1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1.1H4v-3.6h.3a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.9l-.1-.1 2-3 .2.1a1.7 1.7 0 0 0 2-.2A1.7 1.7 0 0 0 10.4 3V2h3.6v1a1.7 1.7 0 0 0 .9 1.5 1.7 1.7 0 0 0 1.9-.3l.2-.1 2 3-.1.1a1.7 1.7 0 0 0-.3 1.9c.2.7.8 1.1 1.5 1.1h.3V14h-.3a1.7 1.7 0 0 0-1.5 1z"/></svg>',
      calendar: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="4" y="5" width="16" height="15" rx="2"/><path d="M8 3v4M16 3v4M4 10h16"/></svg>',
      engine: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M8 8h8l3 3v5h-3l-2 3H9l-2-3H4v-5h3z"/><path d="M9 5h6M12 5v3M20 12h2M2 12h2"/></svg>',
      drivetrain: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="6" cy="6" r="2"/><circle cx="18" cy="6" r="2"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="18" r="2"/><path d="M8 6h8M8 18h8M6 8v8M18 8v8"/></svg>',
      fuel: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M6 3h9v18H6z"/><path d="M15 8h2l2 2v8a2 2 0 0 0 4 0v-6l-3-3"/><path d="M8 7h5"/></svg>'
    };

    const requests = [
      ["Гул под капотом на 2000–3000 оборотах", "Возможные причины: износ подшипника генератора, натяжитель ремня, помпа и др.", "Сегодня, 10:42", "Решено"],
      ["Горит Check Engine", "Ошибка P0420 — эффективность катализатора ниже порога. Рекомендована диагностика выхлопной системы.", "Вчера, 18:15", "Решено"],
      ["Дым из выхлопной трубы", "Возможные причины: износ маслосъемных колпачков, турбина, система EGR.", "12 мая, 14:30", "Решено"],
      ["Быстро разряжается аккумулятор", "Проверить генератор, утечки тока и состояние АКБ. Рекомендована нагрузочная проверка.", "8 мая, 09:12", "Решено"],
      ["Пинки при переключении передач", "Проверить масло в вариаторе, адаптацию CVT, износ ремня или шкивов.", "5 мая, 16:45", "Решено"],
      ["Стук в подвеске спереди справа", "Рекомендована проверка стойки стабилизатора, опорного подшипника и шаровой опоры.", "2 мая, 11:20", "Решено"]
    ];

    const services = [
      ["Замена моторного масла и масляного фильтра", "Масло: 5W-30 Nissan Genuine Oil. Фильтр: оригинальный Nissan", "Сегодня, 10:30", "98 500 км", "violet", "🛢"],
      ["Замена ремня ГРМ с комплектом", "Ремень ГРМ, ролики, натяжитель, помпа. Производитель: Gates", "24 марта 2024", "90 120 км", "green", "⚙"],
      ["Замена воздушного фильтра", "Фильтр воздушный двигателя. Производитель: Mann", "24 марта 2024", "90 120 км", "", "▥"],
      ["Замена передних тормозных колодок", "Колодки передние. Производитель: Brembo", "12 февраля 2024", "86 780 км", "orange", "◎"],
      ["Замена топливного фильтра", "Фильтр топливный. Производитель: Nissan", "10 ноября 2023", "80 450 км", "violet", "▣"],
      ["Обслуживание кондиционера", "Заправка фреоном, проверка герметичности", "5 августа 2023", "74 230 км", "cyan", "❄"]
    ];

    const dtc = [
      ["P0171", "Слишком бедная смесь (Bank 1)", "Система управления двигателем зафиксировала слишком бедную топливно-воздушную смесь.", "Активная", "danger"],
      ["P0401", "Недостаточный поток системы рециркуляции ОГ (EGR)", "Обнаружен недостаточный поток выхлопных газов через клапан рециркуляции.", "Сохраненная", "warn"],
      ["P0202", "Неисправность цепи форсунки цилиндра 2", "Обрыв или короткое замыкание в цепи управления форсункой второго цилиндра.", "Сохраненная", "warn"]
    ];

    const manuals = ["Сервисный мануал", "Мануал по автохимии", "Мануал по дворникам", "Мануал по расходникам", "Тормозная система", "Руководство по эксплуатации", "Электрооборудование", "Система охлаждения", "Подвеска и рулевое"];
    const videos = ["Замена воздушного фильтра Укажите машину", "Замена моторного масла и фильтра Укажите мотор", "Замена передних тормозных колодок", "Замена щеток стеклоочистителя", "Замена цепи ГРМ на Nissan X-Trail Укажите мотор", "Диагностика ошибок с помощью OBD2", "Замена салонного фильтра", "Как снять и заменить аккумулятор"];

    const $ = (selector) => document.querySelector(selector);
    const $$ = (selector) => Array.from(document.querySelectorAll(selector));

    function injectIcons() {
      $$("[data-icon]").forEach((node) => {
        const key = node.dataset.icon;
        if (!iconMap[key]) return;
        if (node.tagName === "BUTTON") node.insertAdjacentHTML("afterbegin", iconMap[key]);
        else node.insertAdjacentHTML("afterbegin", iconMap[key]);
      });
    }

    async function renderLists() {
      const savedHistory = await loadUserHistory();
      const savedRows = savedHistory.map((item) => [item.question, item.answer, item.date, "Сохранено", item.vehicle, item.type]);
      const baseRows = requests.map((item) => [item[0], item[1], item[2], item[3], "Укажите машину", "Демо"]);
      const allRows = savedRows.concat(baseRows);

      $("#journalList").innerHTML = allRows.map((item, index) => `
        <article class="row ${index === 0 ? "featured" : ""}">
          <div class="thumb" aria-hidden="true"></div>
          <div>
            <h3>${escapeHtml(item[0])}</h3>
            <span class="tag">${escapeHtml(item[4] || "Укажите машину")}</span>
            <p>${escapeHtml(item[1]).slice(0, 220)}${String(item[1]).length > 220 ? "..." : ""}</p>
          </div>
          <div><p>${escapeHtml(item[2])}</p><p class="ok">${escapeHtml(item[3])} ✓</p></div>
        </article>
      `).join("");

      $("#historyList").innerHTML = allRows.concat([["Ошибка P0171 слишком бедная смесь", "Укажите машину • Укажите мотор • Укажите топливо", "28 апр., 20:33", "Код ошибки", "Укажите машину", "Код ошибки"]]).map((item, index) => `
        <article class="row" style="grid-template-columns:64px 1fr 150px">
          <div class="square ${item[5] === "Голосовой запрос" ? "violet" : ""}">${item[5] === "Голосовой запрос" ? "🎙" : "⌨"}</div>
          <div><h3>${escapeHtml(item[0])}</h3><p>${escapeHtml(item[4] || "Укажите машину • Укажите мотор • Укажите привод")}</p></div>
          <div><p>${escapeHtml(item[2])}</p><span class="tag">${escapeHtml(item[5] || item[3] || "Текстовый запрос")}</span></div>
        </article>
      `).join("");

      $("#serviceList").innerHTML = services.map((item) => `
        <article class="service">
          <div class="square ${item[4]}">${item[5]}</div>
          <div><h3>${item[0]}</h3><p>${item[1]}</p><p class="ok">Выполнено</p></div>
          <div><p>${item[2]}</p><p>Пробег: ${item[3]}</p></div>
        </article>
      `).join("");

      $("#dtcList").innerHTML = dtc.map((item) => `
        <article class="dtc">
          <div class="dtc-top">
            <div class="code ${item[4]}">⚙ ${item[0]}</div>
            <div><h3>${item[1]}</h3><p>${item[2]}</p></div>
          </div>
          <div class="cols">
            <div><strong>Статус:</strong><br><span class="${item[4]}">${item[3]}</span><br><br><strong>Система:</strong><br>Двигатель / топливная система</div>
            <div><strong>Возможные причины:</strong><br>• Подсос воздуха<br>• Неисправность датчика<br>• Низкое давление топлива<br>• Загрязнение узла</div>
            <div><strong>Рекомендуемые действия:</strong><br>• Проверить разъемы<br>• Провести диагностику<br>• Очистить или заменить узел<br>• Повторно считать ошибки</div>
          </div>
        </article>
      `).join("");

      $("#manualList").innerHTML = manuals.map((title, index) => `
        <article class="manual">
          <h3>${title}</h3>
          <div class="manual-pic" aria-hidden="true"></div>
          <p>PDF • ${(6 + index * 2.1).toFixed(1)} MB</p>
          <p>Материалы адаптированы для Укажите машину.</p>
          <button class="btn blue" data-action="demo">Открыть</button>
        </article>
      `).join("");

      $("#videoList").innerHTML = videos.map((title, index) => `
        <article class="row">
          <div class="thumb" aria-hidden="true"></div>
          <div><h3>${title}</h3><p>Пошаговая инструкция по обслуживанию Укажите машину.</p></div>
          <div><p>${index < 2 ? "Сегодня" : "Май 2024"}</p><span class="tag">${index % 3 === 0 ? "Обслуживание" : index % 3 === 1 ? "Двигатель" : "Диагностика"}</span></div>
        </article>
      `).join("");
    }

    function showView(viewId) {
      $$(".nav button, .view").forEach((node) => node.classList.remove("active"));
      $(`.nav button[data-view="${viewId}"]`).classList.add("active");
      $(`#${viewId}`).classList.add("active");
      document.body.classList.toggle("assistant-mode", viewId === "assistant");
      document.body.classList.toggle("page-mode", viewId !== "assistant");
      syncAssistantMessageHeight();
      if (window.innerWidth < 1050) window.scrollTo({ top: 0, behavior: "smooth" });
    }

    function toast(message) {
      const box = $("#toast");
      box.textContent = message;
      box.classList.add("show");
      clearTimeout(window.__toastTimer);
      window.__toastTimer = setTimeout(() => box.classList.remove("show"), 3600);
    }

    function appendMessage(text, isUser) {
      const div = document.createElement("div");
      div.className = `bubble ${isUser ? "user" : ""}`;
      div.innerHTML = `${linkifyText(text)} <small>${new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}</small>`;
      const messagesBox = $("#messages");
      messagesBox.appendChild(div);
      scrollMessagesToBottom();
      return div;
    }

    function scrollMessagesToBottom() {
      const messagesBox = $("#messages");
      if (!messagesBox) return;
      requestAnimationFrame(() => {
        const isAssistantMode = document.body.classList.contains("assistant-mode");
        const scrollBox = document.body.classList.contains("assistant-mode")
          ? $(".content > .main-panel")
          : messagesBox;

        if (!isAssistantMode && getComputedStyle(messagesBox).overflowY !== "visible") {
          messagesBox.scrollTop = messagesBox.scrollHeight;
          return;
        }

        const lastBubble = messagesBox.querySelector(".bubble:last-child");
        const composer = $(".composer");

        if (!lastBubble || !composer) return;

        if (scrollBox && scrollBox !== messagesBox) {
          scrollBox.scrollTo({ top: scrollBox.scrollHeight, behavior: "smooth" });
        }

        requestAnimationFrame(() => {
          const bubbleBottom = lastBubble.getBoundingClientRect().bottom;
          const composerTop = composer.getBoundingClientRect().top;
          const hiddenByComposer = bubbleBottom - composerTop + 52;

          if (hiddenByComposer <= 0) return;

          if (scrollBox && scrollBox !== messagesBox) {
            scrollBox.scrollBy({ top: hiddenByComposer, behavior: "smooth" });
          } else {
            window.scrollBy({ top: hiddenByComposer, behavior: "smooth" });
          }
        });
      });
    }

    function syncAssistantMessageHeight() {
      const messagesBox = $("#messages");
      const assistantRight = $(".assistant-right");

      if (messagesBox) {
        messagesBox.style.height = "";
        messagesBox.style.maxHeight = "";
      }

      if (assistantRight) assistantRight.style.maxHeight = "";
    }

    function escapeHtml(text) {
      const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" };
      return String(text).replace(/[&<>"']/g, (m) => map[m]);
    }
    function cleanUrl(url) {
      return String(url || "").replace(/[),.;:!?}\]]+$/g, "");
    }

    function linkifyText(text) {
      return escapeHtml(text || "")
        .replace(/(https?:\/\/[^\s<>"']+)/g, (match) => {
          const url = cleanUrl(match);
          const tail = match.slice(url.length);
          return `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>${tail}`;
        })
        .replace(/\n/g, "<br>");
    }

    function extractLinks(text) {
      const raw = String(text || "");
      const matches = raw.match(/https?:\/\/[^\s<>"']+/g) || [];
      const links = [];

      for (const match of matches) {
        const url = cleanUrl(match);
        if (!url || links.some((item) => item.url === url)) continue;

        const index = raw.indexOf(match);
        const before = raw.slice(Math.max(0, index - 260), index);
        const titleMatch = before.match(/"title"\s*:\s*"([^"]+)"/i);
        const forumMatch = before.match(/"forum"\s*:\s*"([^"]+)"/i);
        const hostMatch = url.match(/^https?:\/\/(?:www\.)?([^/]+)/i);
        const isVideo = /youtube\.com|youtu\.be|rutube\.ru|vimeo\.com/i.test(url);

        links.push({
          url,
          title: titleMatch ? titleMatch[1] : (isVideo ? "Видео по теме" : "Ссылка по теме"),
          source: forumMatch ? forumMatch[1] : (hostMatch ? hostMatch[1] : "Материал"),
          isVideo
        });
      }

      return links;
    }

    function updateTopicLinks(answer) {
      const box = $("#topicLinks");
      if (!box) return;

      const links = extractLinks(answer);

      if (!links.length) {
        box.innerHTML = `<p>Ссылки по теме появятся здесь, когда PULS найдет материалы.</p>`;
        return;
      }

      box.innerHTML = links.slice(0, 10).map((item) => `
        <div class="topic-link-item">
          <div class="topic-link-title">${item.isVideo ? "Видео: " : ""}${escapeHtml(item.title)}</div>
          <div>${escapeHtml(item.source)}</div>
          <a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.url)}</a>
        </div>
      `).join("");
    }

    const HISTORY_STORAGE_KEY = "puls_request_history_v1";
    const USER_STORAGE_KEY = "puls_web_user_id_v1";

    function getWebUserId() {
      let userId = localStorage.getItem(USER_STORAGE_KEY);

      if (!userId) {
        userId = "web_" + Date.now() + "_" + Math.random().toString(36).slice(2, 10);
        localStorage.setItem(USER_STORAGE_KEY, userId);
      }

      return userId;
    }

    async function getChatEmail() {
      if (window.supabaseClient?.auth?.getUser) {
        try {
          const { data, error } = await window.supabaseClient.auth.getUser();
          if (!error && data?.user?.email) return data.user.email;
        } catch (error) {
          console.error("PULS auth lookup failed:", error);
        }
      }

      const profileEmail = document.getElementById("profileEmail")?.textContent?.trim() || "";
      if (profileEmail.includes("@")) return profileEmail;

      return `${getWebUserId()}@web.local`;
    }
    function loadLocalHistory() {
      try {
        return JSON.parse(localStorage.getItem(HISTORY_STORAGE_KEY) || "[]");
      } catch (error) {
        return [];
      }
    }

    async function loadUserHistory() {
      return loadLocalHistory();
    }

    async function saveHistoryItem(question, answer) {
      const item = {
        question,
        answer,
        vehicle: "Укажите машину • Укажите мотор • Укажите привод",
        type: "Текстовый запрос"
      };

      const history = loadLocalHistory();
      const now = new Date();
      history.unshift({
        ...item,
        date: now.toLocaleDateString("ru-RU", { day: "2-digit", month: "short" }) + ", " + now.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })
      });
      localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(history.slice(0, 50)));
      await renderLists();
    }

    function updateQuota(quota) {
      if (!quota) return;
      const pill = $(".system-pill");
      if (!pill) return;

      if (quota.unlimited) {
        pill.textContent = "PULS Premium: без лимита";
      } else {
        pill.textContent = `PULS: ${quota.remaining} из ${quota.limit} запросов`;
      }
    }

    function updateKeyChecks(answer) {
      const box = $("#keyChecks");
      if (!box) return;
      const lines = String(answer)
        .split(/\n|•|-|\d+[.)]/)
        .map((line) => line.trim())
        .filter(Boolean);
      const important = lines.filter((line) => /проверь|проверить|начни|датчик|ремень|ролик|генератор|масло|ошиб|obd|свеч|катуш|насос|давлен|egr|турбин|фильтр/i.test(line)).slice(0, 5);
      const finalLines = important.length ? important : lines.slice(0, 4);
      box.innerHTML = finalLines.length
        ? `<ul style="margin:8px 0 0; padding-left:20px; color:var(--soft); line-height:1.6">${finalLines.map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ul>`
        : `<p>Ключевые проверки появятся после ответа PULS.</p>`;
    }

    async function sendPrompt() {
      const input = $("#promptInput");
      const prompt = input.value.trim();
      if (!prompt) return;
      showView("assistant");
      appendMessage(prompt, true);
      input.value = "";

      const loading = appendMessage("PULS анализирует запрос...", false);
      try {
        const email = await getChatEmail();
        const res = await fetch(N8N_WEBHOOK_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: prompt,
            source: "web",
            email,
            language: "ru"
          })
        });

        if (!res.ok) throw new Error("n8n webhook вернул ошибку");

        const rawAnswer = await res.text();
        let data;
        try {
          data = JSON.parse(rawAnswer);
        } catch (error) {
          data = { answer: rawAnswer };
        }

        const answer = data.answer || data.reply || data.message || data.output || rawAnswer || JSON.stringify(data, null, 2);
        loading.innerHTML = `<strong>PULS</strong><br>${linkifyText(answer)} <small>${new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}</small>`;
        updateKeyChecks(answer);
        updateTopicLinks(answer);
        updateQuota(data.quota);
        await saveHistoryItem(prompt, answer);
        await renderLists();
        scrollMessagesToBottom();
      } catch (error) {
        console.error("PULS /chat request failed:", error);
        const errorText = error?.message
          ? `Сервис временно недоступен. ${error.message}`
          : "Сервис временно недоступен. Попробуйте еще раз.";
        loading.innerHTML = `<strong>PULS</strong><br>${errorText} <small>${new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}</small>`;
        updateKeyChecks(errorText);
        await saveHistoryItem(prompt, errorText);
        scrollMessagesToBottom();
      }
    }

    function connectSpline() {
      if (!SPLINE_SCENE_URL) return;
      if (!$("#splineBox")) return;
      $("#splineBox").innerHTML = `<iframe title="Spline scene" src="${SPLINE_SCENE_URL}" allow="autoplay; fullscreen; xr-spatial-tracking"></iframe>`;
    }

    document.addEventListener("DOMContentLoaded", async () => {
      document.body.classList.add("assistant-mode");
      injectIcons();
      await renderLists();
      connectSpline();

      $("#sendBtn").addEventListener("click", sendPrompt);
      $("#promptInput").addEventListener("keydown", (event) => {
        if (event.key === "Enter") sendPrompt();
      });
      window.addEventListener("resize", syncAssistantMessageHeight);
      syncAssistantMessageHeight();
      document.addEventListener("click", (event) => {
        const composerMenuButton = event.target.closest("#composerMenuBtn");
        if (composerMenuButton) {
          event.stopPropagation();
          const menu = $("#composerMenu");
          const isOpen = menu.classList.toggle("show");
          composerMenuButton.setAttribute("aria-expanded", String(isOpen));
          return;
        }

        const viewButton = event.target.closest(".nav button[data-view]");
        if (viewButton) {
          showView(viewButton.dataset.view);
          return;
        }

        const action = event.target.closest("[data-action]")?.dataset.action;
        if (!action) return;
        $("#composerMenu")?.classList.remove("show");
        $("#composerMenuBtn")?.setAttribute("aria-expanded", "false");
        if (event.target.closest("#composerMenuBtn")) return;
        if (action === "dtc") {
          showView("dtc");
          toast("Открыт раздел диагностики по коду.");
        } else if (action === "voice") {
          toast("Голосовой ввод можно подключить к Web Speech API или n8n.");
        } else {
          toast("Это демо-кнопка. Ее можно подключить к n8n, загрузке файлов или базе материалов.");
        }
      });
    });






