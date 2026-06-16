const CHAT_API_URL = "https://puls-backend-t3sn.onrender.com/chat";
const SPLINE_SCENE_URL = "";

    const iconMap = {
      bot: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="5" y="8" width="14" height="10" rx="3"/><path d="M12 4v4M8 13h.01M16 13h.01M7 21h10M3 11v4M21 11v4"/></svg>',
      home: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/></svg>',
      journal: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 7h6M9 11h6M9 15h4"/></svg>',
      history: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v6h6"/><path d="M12 7v5l3 2"/></svg>',
      car: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 13l2-5h12l2 5"/><rect x="3" y="13" width="18" height="6" rx="2"/><path d="M7 19v2M17 19v2M7 16h.01M17 16h.01"/></svg>',
      service: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14 7l3-3 3 3-3 3zM4 20l6-6M6 4l14 14M4 10l6-6"/></svg>',
      mic: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="8" y="3" width="8" height="12" rx="4"/><path d="M5 12a7 7 0 0 0 14 0"/><path d="M12 19v2"/><path d="M8 21h8"/></svg>',
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
    const LANGUAGE_STORAGE_KEY = "puls_language_v1";
    const VEHICLE_STORAGE_KEY = "puls_vehicle_profile_v1";

    const i18n = {
      en: {
        "brand.subtitle": "Your AI assistant for car diagnostics",
        "system.ready": "PULS works for you 24/7",
        "system.freeQuota": "PULS: {remaining} of {limit} requests",
        "system.premium": "PULS Premium: no limit",
        "hero.car": "Select car",
        "hero.year": "Year",
        "hero.yearValue": "Select year",
        "hero.engine": "Engine",
        "hero.engineValue": "Select engine",
        "hero.drive": "Drive",
        "hero.driveValue": "Select drive",
        "hero.fuel": "Fuel type",
        "hero.fuelValue": "Select fuel",
        "nav.car": "My car",
        "nav.journal": "Request log",
        "nav.history": "Request history",
        "nav.dtc": "Errors (DTC)",
        "nav.manuals": "Manuals",
        "nav.video": "Video",
        "nav.settings": "Settings",
        "sound.title": "Noise diagnostics",
        "sound.subtitle": "Like Shazam,<br>but for your car",
        "sound.listening": "Listening...",
        "sound.link": "Record problem sound",
        "sound.text": "Speak or play the noise and I will help identify it",
        "assistant.subtitle": "Ask any question about your car",
        "assistant.demoQuestion": "I hear a humming noise under the hood during acceleration, especially around 2000-3000 rpm.",
        "assistant.demoAnswer": "This looks like a problem with auxiliary engine components. Possible causes: alternator bearing wear, belt tensioner pulley, water pump, or drive belt.",
        "assistant.demoActions": "What you can do:",
        "assistant.demoChecks": "• Check the belt and pulleys<br>• Listen with a stethoscope or long screwdriver<br>• Check pulley and bearing play",
        "assistant.checksTitle": "Summary: what to check",
        "assistant.checksEmpty": "After PULS answers, key checks will appear here.",
        "assistant.linksTitle": "Videos / related links",
        "assistant.linksEmpty": "Links to videos, manuals, and n8n materials will appear here later.",
        "assistant.linksFoundEmpty": "Related links will appear here when PULS finds materials.",
        "assistant.watchVideo": "Watch video",
        "assistant.loading": "PULS is analyzing your request...",
        "assistant.authRequired": "Please sign in or register to ask PULS questions.",
        "assistant.error": "Service is temporarily unavailable. Please try again in a few seconds.",
        "car.title": "My car",
        "car.subtitle": "Information about your car and available materials",
        "car.infoTitle": "Car information",
        "car.model": "Model:",
        "car.year": "Year:",
        "car.engine": "Engine:",
        "car.drive": "Drive:",
        "car.fuel": "Fuel:",
        "car.transmission": "Transmission:",
        "car.transmissionValue": "Select transmission",
        "car.vinValue": "Enter VIN",
        "car.quickTitle": "Quick access",
        "car.quickService": "Maintenance schedule",
        "car.quickSchemes": "Component diagrams",
        "car.quickTorque": "Torque specs",
        "car.quickElectrical": "Wiring diagrams",
        "car.quickFuses": "Fuses",
        "car.specTitle": "Technical specifications",
        "car.serviceTitle": "Service history",
        "car.serviceSubtitle": "Service and maintenance records for the selected car",
        "car.serviceAdd": "Add record",
        "car.serviceHelp": "All maintenance records stay inside the selected car so the assistant always knows what has already been done.",
        "car.photoUpload": "Attach car photo",
        "car.vehicleTitle": "My cars",
        "car.vehicleSubtitle": "Save several vehicles and switch between them without losing context.",
        "car.addVehicle": "Add vehicle",
        "car.deleteVehicle": "Delete vehicle",
        "car.formTitle": "Car profile editor",
        "car.formSubtitle": "Fill in the car once so PULS always knows which vehicle to use.",
        "car.formBrand": "Brand",
        "car.formBrandPlaceholder": "Toyota",
        "car.formModel": "Model",
        "car.formModelPlaceholder": "Land Cruiser",
        "car.formYear": "Year",
        "car.formYearPlaceholder": "2003",
        "car.formEngine": "Engine",
        "car.formEnginePlaceholder": "SR20VET",
        "car.formFuel": "Fuel",
        "car.formFuelPlaceholder": "Petrol",
        "car.formDrive": "Drive",
        "car.formDrivePlaceholder": "4WD",
        "car.formTransmission": "Transmission",
        "car.formTransmissionPlaceholder": "AT",
        "car.formMileage": "Mileage",
        "car.formMileagePlaceholder": "185000 km",
        "car.formVin": "VIN",
        "car.formVinPlaceholder": "JT...",
        "car.formHint": "You can edit the data anytime. Later we can connect VIN or catalog auto-fill here.",
        "car.formSave": "Save car",
        "car.formSaved": "Car profile saved.",
        "car.formDemo": "Fill demo data",
        "car.formLookup": "Decode VIN",
        "car.formLookupHint": "Enter the full VIN and PULS will pull the available vehicle data automatically.",
        "car.lookupReady": "Ready to decode VIN.",
        "car.lookupSearching": "Decoding VIN...",
        "car.lookupNeedVin": "Enter a full 17-character VIN to decode it.",
        "car.lookupInvalid": "This VIN could not be decoded. Please check the number and try again.",
        "car.lookupNotFound": "No matching vehicle data was found for this VIN.",
        "car.lookupError": "VIN lookup failed. Please try again in a few seconds.",
        "spec.displacement": "Engine displacement:",
        "spec.note": "These fields are filled automatically from vehicle data and can be edited manually.",
        "spec.unavailable": "No data",
        "spec.displacementValue": "Auto-filled after car selection",
        "spec.power": "Power:",
        "spec.powerValue": "Auto-filled after car selection",
        "spec.torque": "Torque:",
        "spec.torqueValue": "Auto-filled after car selection",
        "spec.engineType": "Engine type:",
        "spec.engineTypeValue": "Auto-filled after car selection",
        "spec.cylinders": "Cylinders:",
        "spec.cylindersValue": "Auto-filled after car selection",
        "spec.emissions": "Emissions class:",
        "spec.emissionsValue": "Auto-filled after car selection",
        "spec.tank": "Fuel tank:",
        "spec.tankValue": "Auto-filled after car selection",
        "service.title": "Record title",
        "service.description": "Description",
        "service.date": "Date",
        "service.mileage": "Mileage",
        "service.photo": "Photo / sticker",
        "service.previewTitle": "Record sticker preview",
        "service.previewHint": "You can add a photo, or we will show a colored sticker if no photo is attached.",
        "service.save": "Save record",
        "service.saved": "Service record saved.",
        "journal.title": "Request log",
        "journal.subtitle": "History of questions and received solutions",
        "journal.help": "This page stores completed cases only: PULS asked a follow-up, the user confirmed the problem was solved, and the final solution was saved.",
        "journal.empty": "No completed cases yet. A case appears here after the user confirms the issue was solved.",
        "journal.sampleQuestion": "Humming under the hood at 2000-3000 rpm",
        "journal.sampleSolution": "Solved: the alternator belt tensioner pulley was worn. The user replaced the pulley and belt, then confirmed the noise disappeared.",
        "history.title": "Request history",
        "history.subtitle": "Your recent PULS requests",
        "history.help": "This page keeps all of the user's PULS questions. New users start with an empty history.",
        "history.empty": "No request history yet. New PULS questions will appear here after the user signs in and sends them.",
        "dtc.title": "Errors (DTC)",
        "dtc.subtitle": "Diagnostic trouble codes for your car",
        "dtc.clear": "Clear all",
        "dtc.found": "3 errors found.",
        "dtc.warning": "It is recommended to check and fix errors for correct vehicle operation.",
        "manuals.title": "Manuals and guides",
        "manuals.subtitle": "Detailed service guides and recommendations",
        "manuals.help": "Manuals collected from search requests, repair cases, and relevant product documentation for the selected car will appear here.",
        "video.title": "Video",
        "video.subtitle": "History of all videos provided in the chat",
        "video.help": "All videos that appeared in PULS answers are saved here so the user can find them again later.",
        "settings.title": "Settings",
        "settings.subtitle": "Manage your account, subscription, and app",
        "settings.profile": "Profile",
        "settings.subscription": "Subscription",
        "settings.notifications": "Notifications",
        "settings.languageRegion": "Language and region",
        "settings.appLanguage": "App language",
        "settings.units": "Units",
        "settings.unitsValue": "km, °C",
        "settings.metric": "km, °C",
        "settings.imperial": "mi, °F",
        "settings.timezone": "Time zone",
        "subscription.freeStatus": "Status: Free — 10 requests",
        "subscription.plan": "PULS Pro subscription: 100 requests for $15.",
        "subscription.pay": "Pay $15",
        "notifications.service": "Service reminders",
        "notifications.diagnostics": "Diagnostics and errors",
        "notifications.content": "New videos and manuals",
        "notifications.updates": "Promotions and updates",
        "common.on": "On",
        "common.off": "Off",
        "common.filter": "Filter",
        "common.noMatches": "Nothing found for this search.",
        "common.close": "Close",
        "search.requests": "Search requests",
        "search.manuals": "Search manuals",
        "search.video": "Search videos",
        "composer.placeholder": "Describe the problem or ask a question...",
        "composer.attachPhoto": "Attach photo",
        "composer.sendVideo": "Send video",
        "composer.dtc": "Code diagnostics",
        "profile.guest": "Guest",
        "profile.signIn": "Sign in to your account",
        "profile.supabaseMissing": "Supabase is not configured",
        "profile.user": "PULS user",
        "profile.emailMissing": "Email is missing",
        "auth.open": "Sign in / Register",
        "auth.logout": "Log out",
        "auth.deleteProfile": "Delete profile",
        "auth.title": "PULS account",
        "auth.description": "Sign in or register by email to connect your history, subscription, and devices.",
        "auth.newUserHint": "New user? Enter your email and create a new password for the PULS assistant, then click Register.",
        "auth.password": "Password",
        "auth.passwordPlaceholder": "Minimum 6 characters",
        "auth.login": "Sign in",
        "auth.register": "Register",
        "auth.statusReady": "Enter email and password.",
        "auth.statusConfig": "Add Supabase URL and anon key in assets/js/supabaseClient.js.",
        "auth.enterEmail": "Enter email.",
        "auth.enterPassword": "Enter password.",
        "auth.shortPassword": "Password must be at least 6 characters.",
        "auth.registerSuccess": "Registration successful. Check your email to confirm.",
        "auth.signInToDelete": "Sign in before deleting profile.",
        "auth.deleteConfirmPrompt": "Type your email to confirm profile deletion.",
        "auth.deleteCancelled": "Profile deletion cancelled.",
        "auth.deleteRequested": "Profile deletion request saved. Check your email if confirmation is required.",
        "auth.lockedAction": "Sign in or register to use this setting.",
        "toast.dtc": "Code diagnostics section opened.",
        "toast.voice": "Voice input can be connected to Web Speech API or n8n.",
        "toast.demo": "This is a demo button. It can be connected to n8n, uploads, or a materials database.",
        "toast.pay": "Payment will be connected to your checkout provider."
      },
      ru: {
        "brand.subtitle": "Ваш AI-помощник для диагностики автомобиля",
        "system.ready": "PULS работает для вас 24/7",
        "system.freeQuota": "PULS: {remaining} из {limit} запросов",
        "system.premium": "PULS Premium: без лимита",
        "hero.car": "Укажите машину",
        "hero.year": "Год выпуска",
        "hero.yearValue": "Укажите год",
        "hero.engine": "Двигатель",
        "hero.engineValue": "Укажите мотор",
        "hero.drive": "Привод",
        "hero.driveValue": "Укажите привод",
        "hero.fuel": "Тип топлива",
        "hero.fuelValue": "Укажите топливо",
        "nav.car": "Мой автомобиль",
        "nav.journal": "Журнал запросов",
        "nav.history": "История запросов",
        "nav.dtc": "Ошибки (DTC)",
        "nav.manuals": "Мануалы",
        "nav.video": "Видео",
        "nav.settings": "Настройки",
        "sound.title": "Диагностика по шуму",
        "sound.subtitle": "Как Shazam, только<br>для вашего авто",
        "sound.listening": "Слушаю...",
        "sound.link": "Запись звука неполадки",
        "sound.text": "Говорите или воспроизведите шум — я распознаю и помогу",
        "assistant.subtitle": "Задайте любой вопрос о вашем автомобиле",
        "assistant.demoQuestion": "У меня при разгоне появляется гул под капотом, особенно на 2000–3000 оборотах.",
        "assistant.demoAnswer": "Похоже на проблему со вспомогательными узлами двигателя. Вероятные причины: износ подшипника генератора, ролик натяжителя ремня, помпа или приводной ремень.",
        "assistant.demoActions": "Что можно сделать:",
        "assistant.demoChecks": "• Проверьте состояние ремня и роликов<br>• Послушайте шум стетоскопом или длинной отверткой<br>• Проверьте люфт роликов и подшипников",
        "assistant.checksTitle": "Итог: что проверить",
        "assistant.checksEmpty": "После ответа PULS здесь появится краткий список ключевых проверок.",
        "assistant.linksTitle": "Видео / ссылки по теме",
        "assistant.linksEmpty": "Здесь позже будут появляться ссылки на видео, мануалы и материалы из n8n.",
        "assistant.linksFoundEmpty": "Ссылки по теме появятся здесь, когда PULS найдет материалы.",
        "assistant.watchVideo": "Смотреть видео",
        "assistant.loading": "PULS анализирует запрос...",
        "assistant.authRequired": "Войдите или зарегистрируйтесь, чтобы задавать вопросы PULS.",
        "assistant.error": "Сервис временно недоступен. Попробуйте ещё раз через несколько секунд.",
        "car.title": "Мой автомобиль",
        "car.subtitle": "Информация о вашем автомобиле и доступные материалы",
        "car.infoTitle": "Информация об автомобиле",
        "car.model": "Модель:",
        "car.year": "Год выпуска:",
        "car.engine": "Двигатель:",
        "car.drive": "Привод:",
        "car.fuel": "Топливо:",
        "car.transmission": "КПП:",
        "car.transmissionValue": "Укажите КПП",
        "car.vinValue": "Укажите VIN",
        "car.quickTitle": "Быстрый доступ",
        "car.quickService": "Регламент ТО",
        "car.quickSchemes": "Схемы узлов",
        "car.quickTorque": "Моменты затяжки",
        "car.quickElectrical": "Электросхемы",
        "car.quickFuses": "Предохранители",
        "car.specTitle": "Технические характеристики",
        "car.serviceTitle": "Сервис и ТО",
        "car.serviceSubtitle": "История обслуживания и выполненных работ по выбранной машине",
        "car.serviceAdd": "Добавить запись",
        "car.serviceHelp": "Все записи обслуживания и ТО отображаются внутри карточки выбранного автомобиля, чтобы контекст машины не терялся.",
        "car.photoUpload": "Прикрепить фото авто",
        "car.formTitle": "Редактор автомобиля",
        "car.formSubtitle": "Заполните данные машины один раз, чтобы PULS всегда понимал, какой автомобиль использовать.",
        "car.formBrand": "Марка",
        "car.formBrandPlaceholder": "Toyota",
        "car.formModel": "Модель",
        "car.formModelPlaceholder": "Land Cruiser",
        "car.formYear": "Год",
        "car.formYearPlaceholder": "2003",
        "car.formEngine": "Двигатель",
        "car.formEnginePlaceholder": "SR20VET",
        "car.formFuel": "Топливо",
        "car.formFuelPlaceholder": "Бензин",
        "car.formDrive": "Привод",
        "car.formDrivePlaceholder": "4WD",
        "car.formTransmission": "КПП",
        "car.formTransmissionPlaceholder": "АКПП",
        "car.formMileage": "Пробег",
        "car.formMileagePlaceholder": "185000 км",
        "car.formVin": "VIN",
        "car.formVinPlaceholder": "JT...",
        "car.formHint": "Данные можно редактировать в любой момент. Позже сюда можно подключить авто-подтягивание по VIN или каталогу.",
        "car.formSave": "Сохранить машину",
        "car.formSaved": "Профиль машины сохранён.",
        "car.formDemo": "Заполнить пример",
        "car.formLookup": "Распознать VIN",
        "car.formLookupHint": "Введите VIN целиком, и PULS сам подтянет доступные данные по машине.",
        "car.vehicleTitle": "Мои машины",
        "car.vehicleSubtitle": "Сохраняйте несколько автомобилей и переключайтесь между ними без потери контекста.",
        "car.addVehicle": "Добавить автомобиль",
        "car.deleteVehicle": "Удалить автомобиль",
        "car.lookupReady": "Готов к распознаванию VIN.",
        "car.lookupSearching": "Распознаю VIN...",
        "car.lookupNeedVin": "Введите полный VIN из 17 символов, чтобы распознать его.",
        "car.lookupInvalid": "Этот VIN не удалось распознать. Проверьте номер и попробуйте снова.",
        "car.lookupNotFound": "По этому VIN не найдено подходящих данных по машине.",
        "car.lookupError": "Не удалось получить данные по VIN. Попробуйте ещё раз через несколько секунд.",
        "spec.displacement": "Объем двигателя:",
        "spec.note": "Эти поля заполняются автоматически по данным автомобиля и могут редактироваться вручную.",
        "spec.unavailable": "Нет данных",
        "spec.displacementValue": "Заполнится автоматически после выбора авто",
        "spec.power": "Мощность:",
        "spec.powerValue": "Заполнится автоматически после выбора авто",
        "spec.torque": "Крутящий момент:",
        "spec.torqueValue": "Заполнится автоматически после выбора авто",
        "spec.engineType": "Тип двигателя:",
        "spec.engineTypeValue": "Заполнится автоматически после выбора авто",
        "spec.cylinders": "Количество цилиндров:",
        "spec.cylindersValue": "Заполнится автоматически после выбора авто",
        "spec.emissions": "Экологический класс:",
        "spec.emissionsValue": "Заполнится автоматически после выбора авто",
        "spec.tank": "Объем бака:",
        "spec.tankValue": "Заполнится автоматически после выбора авто",
        "service.title": "Название записи",
        "service.description": "Описание",
        "service.date": "Дата",
        "service.mileage": "Пробег",
        "service.photo": "Фото / стикер",
        "service.previewTitle": "Предпросмотр стикера записи",
        "service.previewHint": "Можно добавить фото, а если фото нет, появится цветной стикер.",
        "service.save": "Сохранить запись",
        "service.saved": "Запись ТО сохранена.",
        "journal.title": "Журнал запросов",
        "journal.subtitle": "История обращений и полученных решений",
        "journal.help": "Здесь хранятся только завершенные кейсы: PULS напомнил о проблеме, пользователь подтвердил, что она решена, и финальное решение сохранено.",
        "journal.empty": "Завершенных кейсов пока нет. Кейс появится здесь после подтверждения решения пользователем.",
        "journal.sampleQuestion": "Гул под капотом на 2000–3000 оборотах",
        "journal.sampleSolution": "Решено: износился ролик натяжителя ремня генератора. Пользователь заменил ролик и ремень, затем подтвердил, что гул исчез.",
        "history.title": "История запросов",
        "history.subtitle": "Ваши недавние запросы и обращения к PULSу",
        "history.help": "Здесь хранится вся история вопросов пользователя к PULS. У нового пользователя история пустая.",
        "history.empty": "Истории запросов пока нет. Новые вопросы появятся здесь после входа и отправки запроса.",
        "dtc.title": "Ошибки (DTC)",
        "dtc.subtitle": "Диагностические коды неисправностей вашего автомобиля",
        "dtc.clear": "Удалить все",
        "dtc.found": "Найдено 3 ошибки.",
        "dtc.warning": "Рекомендуется проверить и устранить ошибки для корректной работы автомобиля.",
        "manuals.title": "Мануалы и руководства",
        "manuals.subtitle": "Подробные руководства и рекомендации по обслуживанию",
        "manuals.help": "Здесь собираются общие мануалы по машине, материалы из поисковых запросов, ремонтные инструкции и актуальная продукция для выбранного авто.",
        "video.title": "Видео",
        "video.subtitle": "История всех видеороликов, предоставленных в переписке",
        "video.help": "Здесь сохраняются все видео, которые появлялись в ответах PULS, чтобы пользователь мог быстро найти их снова.",
        "settings.title": "Настройки",
        "settings.subtitle": "Управляйте аккаунтом, подпиской и приложением",
        "settings.profile": "Профиль",
        "settings.subscription": "Подписка",
        "settings.notifications": "Уведомления",
        "settings.languageRegion": "Язык и регион",
        "settings.appLanguage": "Язык приложения",
        "settings.units": "Единицы измерения",
        "settings.unitsValue": "км, °C",
        "settings.metric": "км, °C",
        "settings.imperial": "мили, °F",
        "settings.timezone": "Часовой пояс",
        "subscription.freeStatus": "Статус: Free — 10 запросов",
        "subscription.plan": "Подписка PULS Pro: 100 запросов за $15.",
        "subscription.pay": "Оплатить $15",
        "notifications.service": "Напоминания о ТО",
        "notifications.diagnostics": "Диагностика и ошибки",
        "notifications.content": "Новые видео и мануалы",
        "notifications.updates": "Акции и обновления",
        "common.on": "Вкл",
        "common.off": "Выкл",
        "common.filter": "Фильтр",
        "common.noMatches": "По этому поиску ничего не найдено.",
        "common.close": "Закрыть",
        "search.requests": "Поиск по запросам",
        "search.manuals": "Поиск по мануалам",
        "search.video": "Поиск по видео",
        "composer.placeholder": "Опишите проблему или задайте вопрос...",
        "composer.attachPhoto": "Прикрепить фото",
        "composer.sendVideo": "Отправить видео",
        "composer.dtc": "Диагностика по коду",
        "profile.guest": "Гость",
        "profile.signIn": "Войдите в аккаунт",
        "profile.supabaseMissing": "Supabase не настроен",
        "profile.user": "Пользователь PULS",
        "profile.emailMissing": "Email не указан",
        "auth.open": "Войти / Регистрация",
        "auth.logout": "Выйти",
        "auth.deleteProfile": "Удалить профиль",
        "auth.title": "Аккаунт PULS",
        "auth.description": "Войдите или зарегистрируйтесь по email, чтобы привязать историю, подписку и устройства.",
        "auth.newUserHint": "Если вы новый пользователь, введите свою почту и придумайте новый пароль для ассистента PULS, затем нажмите «Регистрация».",
        "auth.password": "Пароль",
        "auth.passwordPlaceholder": "Минимум 6 символов",
        "auth.login": "Вход",
        "auth.register": "Регистрация",
        "auth.statusReady": "Введите email и пароль.",
        "auth.statusConfig": "Добавьте Supabase URL и anon key в assets/js/supabaseClient.js.",
        "auth.enterEmail": "Введите email.",
        "auth.enterPassword": "Введите пароль.",
        "auth.shortPassword": "Пароль должен быть минимум 6 символов.",
        "auth.registerSuccess": "Регистрация успешна. Проверьте почту для подтверждения.",
        "auth.signInToDelete": "Войдите в аккаунт перед удалением профиля.",
        "auth.deleteConfirmPrompt": "Введите свою почту, чтобы подтвердить удаление профиля.",
        "auth.deleteCancelled": "Удаление профиля отменено.",
        "auth.deleteRequested": "Запрос на удаление профиля сохранен. Проверьте почту, если требуется подтверждение.",
        "auth.lockedAction": "Войдите или зарегистрируйтесь, чтобы использовать эту настройку.",
        "toast.dtc": "Открыт раздел диагностики по коду.",
        "toast.voice": "Голосовой ввод можно подключить к Web Speech API или n8n.",
        "toast.demo": "Это демо-кнопка. Ее можно подключить к n8n, загрузке файлов или базе материалов.",
        "toast.pay": "Оплату можно подключить к вашему платежному провайдеру."
      }
    };

    function getLanguage() {
      try {
        return localStorage.getItem(LANGUAGE_STORAGE_KEY) || "ru";
      } catch (error) {
        return "ru";
      }
    }

    function t(key, params = {}) {
      const lang = getLanguage();
      const template = i18n[lang]?.[key] || i18n.en[key] || key;
      return Object.entries(params).reduce((text, [name, value]) => text.replaceAll(`{${name}}`, value), template);
    }

    window.pulsT = t;

    const VEHICLE_STORE_KEY = "puls_vehicle_store_v1";
    const VEHICLE_LEGACY_KEY = "puls_vehicle_profile_v1";

    function getDefaultVehicleProfile() {
      return {
        id: "",
        brand: "",
        model: "",
        year: "",
        engine: "",
        fuel: "",
        drive: "",
        transmission: "",
        mileage: "",
        vin: "",
        nickname: "",
        photoUrl: "",
        displacement: "",
        power: "",
        torque: "",
        engineType: "",
        cylinders: "",
        emissions: "",
        tank: ""
      };
    }

    function normalizeVehicleProfile(profile = {}) {
      const defaults = getDefaultVehicleProfile();
      return Object.fromEntries(Object.keys(defaults).map((key) => [key, String(profile[key] ?? defaults[key] ?? "").trim()]));
    }

    function mergeVehicleProfiles(primary = {}, fallback = {}) {
      const defaults = getDefaultVehicleProfile();
      const merged = {};
      Object.keys(defaults).forEach((key) => {
        const primaryValue = String(primary[key] ?? "").trim();
        const fallbackValue = String(fallback[key] ?? "").trim();
        merged[key] = primaryValue || fallbackValue;
      });
      return normalizeVehicleProfile(merged);
    }

    function createVehicleId() {
      return `veh_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    }

    function normalizeVehicleStore(store = {}) {
      const rawVehicles = Array.isArray(store.vehicles) ? store.vehicles : [];
      let vehicles = rawVehicles.length ? rawVehicles : [];

      if (!vehicles.length && store && typeof store === "object" && !Array.isArray(store)) {
        const looksLikeProfile = ["brand", "model", "year", "engine", "fuel", "drive", "transmission", "mileage", "vin"]
          .some((key) => String(store[key] || "").trim());
        if (looksLikeProfile) vehicles = [store];
      }

      vehicles = vehicles.map((vehicle, index) => normalizeVehicleProfile({
        ...vehicle,
        id: vehicle.id || vehicle.vehicleId || `${index}_${vehicle.vin || vehicle.model || "vehicle"}`
      }));

      const activeId = String(store.activeId || store.activeVehicleId || vehicles[0]?.id || "").trim();
      if (!vehicles.length) {
        const fallback = normalizeVehicleProfile({ id: createVehicleId() });
        vehicles = [fallback];
      }

      const safeActiveId = vehicles.some((vehicle) => vehicle.id === activeId) ? activeId : vehicles[0].id;
      return { activeId: safeActiveId, vehicles };
    }

    function loadVehicleStore() {
      try {
        const raw = localStorage.getItem(VEHICLE_STORE_KEY);
        if (raw) return normalizeVehicleStore(JSON.parse(raw));

        const legacyRaw = localStorage.getItem(VEHICLE_LEGACY_KEY);
        if (legacyRaw) {
          const profile = normalizeVehicleProfile(JSON.parse(legacyRaw));
          const withId = { ...profile, id: createVehicleId() };
          const store = { activeId: withId.id, vehicles: [withId] };
          localStorage.setItem(VEHICLE_STORE_KEY, JSON.stringify(store));
          return store;
        }

        return normalizeVehicleStore();
      } catch (error) {
        return normalizeVehicleStore();
      }
    }

    function saveVehicleStore(store) {
      try {
        localStorage.setItem(VEHICLE_STORE_KEY, JSON.stringify(normalizeVehicleStore(store)));
      } catch (error) {
        console.warn("Could not save vehicle store:", error);
      }
    }

    function loadVehicleProfile() {
      const store = loadVehicleStore();
      return store.vehicles.find((vehicle) => vehicle.id === store.activeId) || store.vehicles[0] || getDefaultVehicleProfile();
    }

    function saveVehicleProfile(profile, { activate = true } = {}) {
      if (!requireSignedInForEdit()) return loadVehicleProfile();
      const store = loadVehicleStore();
      const targetId = String(profile?.id || store.activeId || createVehicleId()).trim();
      const index = store.vehicles.findIndex((vehicle) => vehicle.id === targetId);
      const existing = index >= 0 ? store.vehicles[index] : getDefaultVehicleProfile();
      const normalized = normalizeVehicleProfile({
        ...existing,
        ...profile,
        id: String(existing.id || targetId).trim()
      });
      if (index >= 0) {
        store.vehicles[index] = normalized;
      } else {
        store.vehicles.unshift(normalized);
      }
      if (activate) store.activeId = normalized.id;
      saveVehicleStore(store);
      return normalized;
    }

    function addVehicleProfile(profile = {}) {
      if (!requireSignedInForEdit()) return loadVehicleProfile();
      const store = loadVehicleStore();
      const vehicle = normalizeVehicleProfile({ ...getDefaultVehicleProfile(), ...profile, id: createVehicleId() });
      store.vehicles.unshift(vehicle);
      store.activeId = vehicle.id;
      saveVehicleStore(store);
      return vehicle;
    }

    function setActiveVehicleProfile(vehicleId) {
      const store = loadVehicleStore();
      const exists = store.vehicles.find((vehicle) => vehicle.id === vehicleId);
      if (!exists) return loadVehicleProfile();
      store.activeId = vehicleId;
      saveVehicleStore(store);
      return exists;
    }

    function removeActiveVehicleProfile() {
      if (!requireSignedInForEdit()) return loadVehicleProfile();
      const store = loadVehicleStore();
      if (store.vehicles.length <= 1) {
        const blank = normalizeVehicleProfile({ id: createVehicleId() });
        const nextStore = { activeId: blank.id, vehicles: [blank] };
        saveVehicleStore(nextStore);
        return blank;
      }

      const activeIndex = store.vehicles.findIndex((vehicle) => vehicle.id === store.activeId);
      const nextVehicles = store.vehicles.filter((vehicle) => vehicle.id !== store.activeId);
      const nextActive = nextVehicles[Math.max(0, activeIndex - 1)] || nextVehicles[0];
      const nextStore = { activeId: nextActive.id, vehicles: nextVehicles };
      saveVehicleStore(nextStore);
      return nextActive;
    }

    const VIN_LOOKUP_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/";
    const VIN_LOOKUP_CACHE_KEY = "puls_vin_lookup_v1";
    let vehicleLookupTimer = null;
    let vehicleLookupRequestId = 0;

    function getVinLookupCache(vin) {
      try {
        const raw = localStorage.getItem(`${VIN_LOOKUP_CACHE_KEY}:${vin}`);
        return raw ? JSON.parse(raw) : null;
      } catch (error) {
        return null;
      }
    }

    function setVinLookupCache(vin, data) {
      try {
        localStorage.setItem(`${VIN_LOOKUP_CACHE_KEY}:${vin}`, JSON.stringify(data));
      } catch (error) {
        console.warn("Could not save VIN cache:", error);
      }
    }

    function isFullVin(vin) {
      return /^[A-HJ-NPR-Z0-9]{17}$/i.test(String(vin || "").trim());
    }

    function decodeVinRecord(record = {}) {
      const normalized = {
        brand: String(record.Make || record.Manufacturer || record.ManufacturerName || "").trim(),
        model: String(
          record.Model ||
          record.BaseModelName ||
          record.ModelName ||
          record.Series ||
          record.Series2 ||
          record.Trim ||
          record.Trim2 ||
          record.VehicleDescriptor ||
          ""
        ).trim(),
        year: String(record.ModelYear || "").trim(),
        engine: String(record.EngineModel || record.EngineConfiguration || record.EngineDescription || "").trim(),
        fuel: String(record.FuelTypePrimary || record.FuelTypeSecondary || "").trim(),
        drive: String(record.DriveType || "").trim(),
        transmission: String(record.TransmissionStyle || "").trim(),
        displacement: String(record.DisplacementL || "").trim(),
        power: String(record.EngineHP || "").trim(),
        torque: String(record.EngineTorque || "").trim(),
        engineType: String(record.EngineConfiguration || record.EngineDescription || record.EngineModel || "").trim(),
        cylinders: String(record.EngineCylinders || "").trim(),
        emissions: String(record.EmissionsStandard || record.EmissionsInfo || "").trim(),
        tank: String(record.FuelTankVolume || record.FuelTankLocation || "").trim(),
        mileage: "",
        vin: String(record.VIN || record.Vin || "").trim().toUpperCase()
      };

      return normalizeVehicleProfile(normalized);
    }

    function updateLookupStatus(message, state = "info") {
      const node = $("#carLookupStatus");
      if (!node) return;
      node.dataset.state = state;
      node.textContent = message || "";
    }

    async function lookupVehicleByVin(vin, { force = false } = {}) {
      const normalizedVin = String(vin || "").trim().toUpperCase();
      if (!isFullVin(normalizedVin)) {
        updateLookupStatus(t("car.lookupNeedVin"), "warn");
        return null;
      }

      const cached = getVinLookupCache(normalizedVin);
      if (cached && !force) {
        const current = loadVehicleProfile();
        const preserveManualEdits = String(current.vin || "").trim().toUpperCase() === normalizedVin;
        const mergedCached = preserveManualEdits
          ? mergeVehicleProfiles(current, { ...cached, vin: normalizedVin })
          : mergeVehicleProfiles({ ...cached, vin: normalizedVin }, current);
        mergedCached.id = current.id;
        fillVehicleForm(mergedCached);
        saveVehicleProfile(mergedCached);
        updateLookupStatus(t("car.lookupReady"), "ok");
        return mergedCached;
      }

      const requestId = ++vehicleLookupRequestId;
      updateLookupStatus(t("car.lookupSearching"), "info");

      try {
        const response = await fetch(`${VIN_LOOKUP_URL}${encodeURIComponent(normalizedVin)}?format=json`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        if (requestId !== vehicleLookupRequestId) return null;

        const record = Array.isArray(data?.Results) ? data.Results[0] : null;
        if (!record) {
          updateLookupStatus(t("car.lookupNotFound"), "warn");
          return null;
        }

        const errorCode = String(record.ErrorCode || "").trim();
        const hasUsefulFields = Boolean(record.Make || record.Model || record.ModelYear || record.EngineModel);
        if (errorCode && errorCode !== "0" && errorCode !== "1" && !hasUsefulFields) {
          updateLookupStatus(t("car.lookupInvalid"), "warn");
          return null;
        }

        const decoded = decodeVinRecord({ ...record, VIN: normalizedVin });
        const previous = loadVehicleProfile();
        const keepPreviousModel = Boolean(previous.model && previous.brand && decoded.brand && previous.brand === decoded.brand);
        const preserveManualEdits = String(previous.vin || "").trim().toUpperCase() === normalizedVin;
        const lookupData = {
          ...decoded,
          model: decoded.model || (keepPreviousModel ? previous.model : ""),
          vin: normalizedVin
        };
        const merged = preserveManualEdits
          ? mergeVehicleProfiles(previous, lookupData)
          : mergeVehicleProfiles(lookupData, previous);
        merged.id = previous.id;

        setVinLookupCache(normalizedVin, merged);
        fillVehicleForm(merged);
        saveVehicleProfile(merged);
        updateLookupStatus(t("car.formSaved"), "ok");
        renderLists();
        return merged;
      } catch (error) {
        console.error("VIN lookup failed:", error);
        updateLookupStatus(t("car.lookupError"), "error");
        return null;
      }
    }

    function getVehicleLabel(profile = loadVehicleProfile()) {
      const normalized = normalizeVehicleProfile(profile);
      return [normalized.brand, normalized.model].filter(Boolean).join(" ").trim() || t("hero.car");
    }

    function setCarSummaryText(profile = loadVehicleProfile()) {
      const normalized = normalizeVehicleProfile(profile);
      const summary = getVehicleLabel(normalized);
      const yearText = normalized.year || t("hero.yearValue");
      const engineText = normalized.engine || t("hero.engineValue");
      const driveText = normalized.drive || t("hero.driveValue");
      const fuelText = normalized.fuel || t("hero.fuelValue");
      const transmissionText = normalized.transmission || t("car.transmissionValue");
      const vinText = normalized.vin || t("car.vinValue");

      const setNodeText = (selector, value) => {
        const node = $(selector);
        if (node) node.textContent = value;
      };

      setNodeText("#heroCarTitle", summary);
      setNodeText("#heroYearValue", yearText);
      setNodeText("#heroEngineValue", engineText);
      setNodeText("#heroDriveValue", driveText);
      setNodeText("#heroFuelValue", fuelText);
      setNodeText("#carInfoModel", summary);
      setNodeText("#carInfoYear", yearText);
      setNodeText("#carInfoEngine", engineText);
      setNodeText("#carInfoDrive", driveText);
      setNodeText("#carInfoFuel", fuelText);
      setNodeText("#carInfoTransmission", transmissionText);
      setNodeText("#carInfoVin", vinText);

      const setSpecField = (selector, value, placeholder) => {
        const node = $(selector);
        if (!node) return;
        if ("value" in node) {
          node.value = value || "";
          node.placeholder = placeholder;
        } else {
          node.textContent = value || placeholder;
        }
      };

      setSpecField("#specDisplacement", normalized.displacement, t("spec.displacementValue"));
      setSpecField("#specPower", normalized.power, t("spec.powerValue"));
      setSpecField("#specTorque", normalized.torque, t("spec.torqueValue"));
      setSpecField("#specEngineType", normalized.engineType, t("spec.engineTypeValue"));
      setSpecField("#specCylinders", normalized.cylinders, t("spec.cylindersValue"));
      setSpecField("#specEmissions", normalized.emissions, t("spec.emissionsValue"));
      setSpecField("#specTank", normalized.tank, t("spec.tankValue"));

      const formStatus = $("#carFormStatus");
      if (formStatus && formStatus.dataset.state === "saved") {
        formStatus.textContent = t("car.formSaved");
      }
    }

    function setCarPhotoPreview(photoUrl = "") {
      const box = $(".car-photo-upload");
      if (!box) return;
      if (!photoUrl) {
        box.style.removeProperty("--car-photo-image");
        box.classList.remove("has-photo");
        return;
      }

      box.style.setProperty("--car-photo-image", `url("${photoUrl}")`);
      box.classList.add("has-photo");
    }

    function getVehicleFormValues() {
      const active = loadVehicleProfile();
      return normalizeVehicleProfile({
        id: active.id,
        brand: $("#carBrandInput")?.value,
        model: $("#carModelInput")?.value,
        year: $("#carYearInput")?.value,
        engine: $("#carEngineInput")?.value,
        fuel: $("#carFuelInput")?.value,
        drive: $("#carDriveInput")?.value,
        transmission: $("#carTransmissionInput")?.value,
        mileage: $("#carMileageInput")?.value,
        vin: $("#carVinInput")?.value,
        photoUrl: active.photoUrl || "",
        nickname: active.nickname || "",
        displacement: $("#specDisplacement")?.value,
        power: $("#specPower")?.value,
        torque: $("#specTorque")?.value,
        engineType: $("#specEngineType")?.value,
        cylinders: $("#specCylinders")?.value,
        emissions: $("#specEmissions")?.value,
        tank: $("#specTank")?.value
      });
    }

    function fillVehicleForm(profile = loadVehicleProfile()) {
      const normalized = normalizeVehicleProfile(profile);
      const mapping = {
        "#carBrandInput": normalized.brand,
        "#carModelInput": normalized.model,
        "#carYearInput": normalized.year,
        "#carEngineInput": normalized.engine,
        "#carFuelInput": normalized.fuel,
        "#carDriveInput": normalized.drive,
        "#carTransmissionInput": normalized.transmission,
        "#carMileageInput": normalized.mileage,
        "#carVinInput": normalized.vin
      };
      Object.entries(mapping).forEach(([selector, value]) => {
        const node = $(selector);
        if (node) node.value = value;
      });
      setCarPhotoPreview(normalized.photoUrl);
      setCarSummaryText(normalized);
    }

    function initVehicleEditor() {
      const form = $("#carForm");
      if (!form) return;

      const initialProfile = loadVehicleProfile();
      fillVehicleForm(initialProfile);
      if (initialProfile.vin && isFullVin(initialProfile.vin)) {
        updateLookupStatus(t("car.lookupSearching"), "info");
        setTimeout(() => lookupVehicleByVin(initialProfile.vin), 50);
      } else {
        updateLookupStatus(t("car.lookupReady"), "info");
      }

      const saveProfile = (profile, state = "saved") => {
        if (!isSignedIn()) {
          requireSignedInForEdit();
          return;
        }
        saveVehicleProfile(profile);
        const status = $("#carFormStatus");
        if (status) {
          status.dataset.state = state;
          status.textContent = state === "saved" ? t("car.formSaved") : "";
        }
        setCarSummaryText(profile);
      };

      form.addEventListener("submit", (event) => {
        event.preventDefault();
        saveProfile(getVehicleFormValues());
      });

      form.addEventListener("input", () => {
        saveProfile(getVehicleFormValues(), "typing");
      });

      ["#specDisplacement", "#specPower", "#specTorque", "#specEngineType", "#specCylinders", "#specEmissions", "#specTank"].forEach((selector) => {
        $(selector)?.addEventListener("input", () => {
          saveProfile(getVehicleFormValues(), "typing");
        });
      });

      $("#carLookupBtn")?.addEventListener("click", () => {
        lookupVehicleByVin($("#carVinInput")?.value);
      });

      $("#carVinInput")?.addEventListener("input", () => {
        clearTimeout(vehicleLookupTimer);
        const vin = $("#carVinInput")?.value || "";
        if (!vin.trim()) {
          updateLookupStatus(t("car.lookupReady"), "info");
          return;
        }
        if (!isFullVin(vin)) {
          updateLookupStatus(t("car.lookupNeedVin"), "warn");
          return;
        }
        vehicleLookupTimer = setTimeout(() => lookupVehicleByVin(vin), 650);
      });

      $("#carVinInput")?.addEventListener("blur", () => {
        clearTimeout(vehicleLookupTimer);
        const vin = $("#carVinInput")?.value || "";
        if (isFullVin(vin)) {
          lookupVehicleByVin(vin);
        }
      });

      $("#carFillDemoBtn")?.addEventListener("click", () => {
        const demo = normalizeVehicleProfile({
          brand: "Nissan",
          model: "X-Trail",
          year: "2003",
          engine: "SR20VET",
          fuel: "Petrol",
          drive: "4WD",
          transmission: "AT",
          mileage: "185000 km",
          vin: "JT1234567890"
        });
        fillVehicleForm(demo);
        saveProfile(demo);
      });
    }

    function setTranslatedContent(node, value) {
      if (node.firstElementChild?.tagName?.toLowerCase() === "svg") {
        Array.from(node.childNodes).forEach((child) => {
          if (child !== node.firstElementChild) child.remove();
        });
        node.appendChild(document.createTextNode(value));
        return;
      }

      node.innerHTML = value;
    }

    function applyLanguage() {
      const lang = getLanguage();
      document.documentElement.lang = lang;
      $$("[data-i18n]").forEach((node) => setTranslatedContent(node, t(node.dataset.i18n)));
      $$("[data-i18n-placeholder]").forEach((node) => {
        node.setAttribute("placeholder", t(node.dataset.i18nPlaceholder));
      });
      $$("[data-i18n-aria-label]").forEach((node) => {
        node.setAttribute("aria-label", t(node.dataset.i18nAriaLabel));
      });
      const languageSelect = $("#languageSelect");
      if (languageSelect) languageSelect.value = lang;
      window.updateProfileBlock?.();
      applyAuthLockedState();
    }

    function setLanguage(lang) {
      try {
        localStorage.setItem(LANGUAGE_STORAGE_KEY, lang);
      } catch (error) {
        console.warn("Could not save language preference:", error);
      }
      applyLanguage();
      renderLists();
    }

    function toggleHelp(name) {
      const help = document.getElementById(`${name}Help`);
      if (!help) return;
      help.classList.toggle("show");
    }

    async function updateCarPhoto(file) {
      if (!requireSignedInForEdit()) return "";
      if (!file) {
        setCarPhotoPreview("");
        return "";
      }

      const url = await fileToDataUrl(file);
      if (!url) return "";
      setCarPhotoPreview(url);
      const active = loadVehicleProfile();
      saveVehicleProfile({ ...active, photoUrl: url });
      setCarSummaryText({ ...active, photoUrl: url });
      return url;
    }

    function isSignedIn() {
      return Boolean(window.pulsCurrentUser);
    }

    function requireSignedInForEdit() {
      if (isSignedIn()) return true;
      toast(t("auth.lockedAction"));
      window.openAuthModal?.();
      return false;
    }

    function applyAuthLockedState() {
      const signedIn = isSignedIn();
      $$(".auth-required").forEach((node) => {
        node.classList.toggle("locked", !signedIn);
        if ("disabled" in node) node.disabled = !signedIn;
        const input = node.matches(".car-photo-upload") ? node.querySelector("input") : null;
        if (input) input.disabled = !signedIn;
        node.setAttribute("aria-disabled", String(!signedIn));
      });
      ["#carForm", "#serviceForm"].forEach((selector) => {
        const form = $(selector);
        if (!form) return;
        form.querySelectorAll("input, button, select, textarea").forEach((node) => {
          node.disabled = !signedIn;
        });
      });
    }

    function guardAuthAction(target) {
      if (!target.closest(".auth-required") || isSignedIn()) return false;
      toast(t("auth.lockedAction"));
      window.openAuthModal?.();
      return true;
    }

    function injectIcons() {
      $$("[data-icon]").forEach((node) => {
        const key = node.dataset.icon;
        if (!iconMap[key]) return;
        if (node.tagName === "BUTTON") node.insertAdjacentHTML("afterbegin", iconMap[key]);
        else node.insertAdjacentHTML("afterbegin", iconMap[key]);
      });
    }

    function getSearchValue(id) {
      return ($(id)?.value || "").trim().toLowerCase();
    }

    function matchesSearch(values, query) {
      if (!query) return true;
      return values.some((value) => String(value || "").toLowerCase().includes(query));
    }

    function emptyState(message) {
      return `<div class="empty-state">${escapeHtml(message)}</div>`;
    }

    const requestModalState = {
      visibleHistory: [],
      visibleJournal: []
    };

    function getRequestModalNodes() {
      return {
        modal: $("#requestModal"),
        title: $("#requestModalTitle"),
        meta: $("#requestModalMeta"),
        type: $("#requestModalType"),
        status: $("#requestModalStatus"),
        question: $("#requestModalQuestion"),
        answer: $("#requestModalAnswer"),
        links: $("#requestModalLinks")
      };
    }

    function closeRequestModal() {
      const { modal } = getRequestModalNodes();
      if (!modal) return;
      modal.classList.remove("show");
      modal.setAttribute("aria-hidden", "true");
    }

    function renderRequestLinks(links) {
      if (!links.length) {
        return `<p class="request-empty">${escapeHtml(getLanguage() === "en" ? "No links found." : "Ссылки не найдены.")}</p>`;
      }

      return links.map((item) => `
        <a class="request-link" href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">
          <strong>${escapeHtml(item.title || (getLanguage() === "en" ? "Related link" : "Ссылка по теме"))}</strong>
          <span>${escapeHtml(item.description || item.url)}</span>
          <small>${escapeHtml(item.url)}</small>
        </a>
      `).join("");
    }

    function openRequestModal(item) {
      if (!item) return;
      const nodes = getRequestModalNodes();
      if (!nodes.modal) return;

      const english = getLanguage() === "en";
      const normalizedLinks = normalizeResponseLinks(item.links || []);
      const links = normalizedLinks.length ? normalizedLinks : extractLinks(item.answer || "");

      if (nodes.title) nodes.title.textContent = english ? "Request details" : "Детали запроса";
      if (nodes.meta) nodes.meta.textContent = [item.date, item.vehicle].filter(Boolean).join(" • ");
      if (nodes.type) nodes.type.textContent = item.type || (english ? "Text request" : "Текстовый запрос");
      if (nodes.status) nodes.status.textContent = item.status || "new";
      if (nodes.question) nodes.question.innerHTML = linkifyText(item.question || "");
      if (nodes.answer) nodes.answer.innerHTML = linkifyText(item.answer || "");
      if (nodes.links) nodes.links.innerHTML = renderRequestLinks(links);

      nodes.modal.classList.add("show");
      nodes.modal.setAttribute("aria-hidden", "false");
    }

    function openRequestByClick(target) {
      const card = target.closest("[data-request-kind][data-request-index]");
      if (!card) return false;

      const kind = card.dataset.requestKind;
      const index = Number(card.dataset.requestIndex);
      if (!Number.isFinite(index)) return false;

      const source = kind === "journal" ? requestModalState.visibleJournal : requestModalState.visibleHistory;
      const item = source[index];
      if (!item) return false;

      openRequestModal(item);
      return true;
    }

    async function renderLists() {
      const english = getLanguage() === "en";
      const vehicleProfile = loadVehicleProfile();
      const selectCar = getVehicleLabel(vehicleProfile);
      const selectYear = vehicleProfile.year || t("hero.yearValue");
      const selectEngine = vehicleProfile.engine || t("hero.engineValue");
      const selectDrive = vehicleProfile.drive || t("hero.driveValue");
      const serviceRows = english ? [
        ["Engine oil and oil filter replacement", "Oil: 5W-30 Nissan Genuine Oil. Filter: original Nissan", "Today, 10:30", "98,500 km", "violet", "🛢"],
        ["Timing belt kit replacement", "Timing belt, rollers, tensioner, water pump. Manufacturer: Gates", "March 24, 2024", "90,120 km", "green", "⚙"],
        ["Air filter replacement", "Engine air filter. Manufacturer: Mann", "March 24, 2024", "90,120 km", "", "▥"],
        ["Front brake pad replacement", "Front brake pads. Manufacturer: Brembo", "February 12, 2024", "86,780 km", "orange", "◎"],
        ["Fuel filter replacement", "Fuel filter. Manufacturer: Nissan", "November 10, 2023", "80,450 km", "violet", "▣"],
        ["A/C service", "Freon refill and leak check", "August 5, 2023", "74,230 km", "cyan", "❄"]
      ] : services;
      const dtcRows = english ? [
        ["P0171", "System too lean (Bank 1)", "The engine control system detected a lean air-fuel mixture.", "Active", "danger"],
        ["P0401", "EGR flow insufficient", "Insufficient exhaust gas flow through the EGR valve was detected.", "Stored", "warn"],
        ["P0202", "Cylinder 2 injector circuit malfunction", "Open or short circuit in the second cylinder injector control circuit.", "Stored", "warn"]
      ] : dtc;
      const manualRows = english ? ["Service manual", "Car chemicals manual", "Wiper manual", "Consumables guide", "Brake system", "Owner's manual", "Electrical system", "Cooling system", "Suspension and steering"] : manuals;
      const videoRows = english ? ["Air filter replacement Select car", "Engine oil and filter replacement Select engine", "Front brake pad replacement", "Wiper blade replacement", "Timing chain replacement on Nissan X-Trail Select engine", "OBD2 error diagnostics", "Cabin filter replacement", "How to remove and replace a battery"] : videos;
      const textRequestLabel = english ? "Text request" : "Текстовый запрос";
      const voiceRequestLabel = english ? "Voice request" : "Голосовой запрос";
      const completedLabel = english ? "Completed" : "Выполнено";
      const systemLabel = english ? "System:" : "Система:";
      const possibleCausesLabel = english ? "Possible causes:" : "Возможные причины:";
      const actionsLabel = english ? "Recommended actions:" : "Рекомендуемые действия:";

      const savedHistory = await loadUserHistory();
      const historyRows = savedHistory.map((item) => ({
        question: item.question,
        answer: item.answer,
        links: item.links || [],
        date: item.date,
        vehicle: item.vehicle || [selectCar, selectYear, selectEngine, selectDrive].filter(Boolean).join(" • "),
        type: item.type || textRequestLabel,
        status: item.status || "new"
      }));
      const solvedStatuses = ["solved", "resolved", "closed", "done", "completed", "решено", "закрыто"];
      const solvedHistory = historyRows.filter((item) => solvedStatuses.includes(String(item.status).toLowerCase()));
      const closedCases = solvedHistory.length ? solvedHistory.map((item) => ({
        question: item.question,
        answer: item.answer,
        date: item.date,
        vehicle: item.vehicle,
        status: completedLabel
      })) : [{
        question: t("journal.sampleQuestion"),
        answer: t("journal.sampleSolution"),
        date: english ? "Example" : "Пример",
        vehicle: selectCar,
        status: completedLabel
      }];

      const journalQuery = getSearchValue("#journalSearch");
      const visibleCases = closedCases.filter((item) => matchesSearch([item.question, item.answer, item.vehicle, item.status], journalQuery));
      requestModalState.visibleJournal = visibleCases;
      $("#journalList").innerHTML = visibleCases.length ? visibleCases.map((item, index) => `
        <article class="row request-row ${index === 0 ? "featured" : ""}" data-request-kind="journal" data-request-index="${index}" role="button" tabindex="0">
          <div class="thumb" aria-hidden="true"></div>
          <div>
            <h3>${escapeHtml(item.question)}</h3>
            <span class="tag">${escapeHtml(item.vehicle)}</span>
            <p>${escapeHtml(item.answer)}</p>
          </div>
          <div><p>${escapeHtml(item.date)}</p><p class="ok">${escapeHtml(item.status)} ✓</p></div>
        </article>
      `).join("") : emptyState(journalQuery ? t("common.noMatches") : t("journal.empty"));

      const historyQuery = getSearchValue("#historySearch");
      const visibleHistory = historyRows.filter((item) => matchesSearch([item.question, item.answer, item.vehicle, item.type, item.date], historyQuery));
      requestModalState.visibleHistory = visibleHistory;
      $("#historyList").innerHTML = visibleHistory.length ? visibleHistory.map((item, index) => `
        <article class="row request-row" style="grid-template-columns:64px 1fr 150px" data-request-kind="history" data-request-index="${index}" role="button" tabindex="0">
          <div class="square ${item.type === voiceRequestLabel ? "violet" : ""}">${item.type === voiceRequestLabel ? "🎙" : "⌨"}</div>
          <div><h3>${escapeHtml(item.question)}</h3><p>${escapeHtml(item.vehicle)}</p></div>
          <div><p>${escapeHtml(item.date)}</p><span class="tag">${escapeHtml(item.type)}</span></div>
        </article>
      `).join("") : emptyState(historyQuery ? t("common.noMatches") : t("history.empty"));

      const serviceList = $("#serviceList");
      if (serviceList) {
        serviceList.innerHTML = serviceRows.map((item) => `
          <article class="service">
            <div class="square ${item[4]}">${item[5]}</div>
            <div><h3>${item[0]}</h3><p>${item[1]}</p><p class="ok">${completedLabel}</p></div>
            <div><p>${item[2]}</p><p>${english ? "Mileage" : "Пробег"}: ${item[3]}</p></div>
          </article>
        `).join("");
      }

      setCarSummaryText(vehicleProfile);
      renderVehicleSwitcher();
      renderServiceRecords(vehicleProfile);

      $("#dtcList").innerHTML = dtcRows.map((item) => `
        <article class="dtc">
          <div class="dtc-top">
            <div class="code ${item[4]}">⚙ ${item[0]}</div>
            <div><h3>${item[1]}</h3><p>${item[2]}</p></div>
          </div>
          <div class="cols">
            <div><strong>${english ? "Status:" : "Статус:"}</strong><br><span class="${item[4]}">${item[3]}</span><br><br><strong>${systemLabel}</strong><br>${english ? "Engine / fuel system" : "Двигатель / топливная система"}</div>
            <div><strong>${possibleCausesLabel}</strong><br>${english ? "• Air leak<br>• Sensor malfunction<br>• Low fuel pressure<br>• Dirty component" : "• Подсос воздуха<br>• Неисправность датчика<br>• Низкое давление топлива<br>• Загрязнение узла"}</div>
            <div><strong>${actionsLabel}</strong><br>${english ? "• Check connectors<br>• Run diagnostics<br>• Clean or replace component<br>• Read errors again" : "• Проверить разъемы<br>• Провести диагностику<br>• Очистить или заменить узел<br>• Повторно считать ошибки"}</div>
          </div>
        </article>
      `).join("");

      const manualQuery = getSearchValue("#manualSearch");
      const visibleManuals = manualRows
        .map((title, index) => ({ title, index }))
        .filter((item) => matchesSearch([item.title], manualQuery));
      $("#manualList").innerHTML = visibleManuals.length ? visibleManuals.map(({ title, index }) => `
        <article class="manual">
          <h3>${title}</h3>
          <div class="manual-pic" aria-hidden="true"></div>
          <p>PDF • ${(6 + index * 2.1).toFixed(1)} MB</p>
          <p>${english ? `Materials adapted for ${selectCar}.` : `Материалы адаптированы для ${selectCar}.`}</p>
          <button class="btn blue" data-action="demo">${english ? "Open" : "Открыть"}</button>
        </article>
      `).join("") : emptyState(t("common.noMatches"));

      const videoQuery = getSearchValue("#videoSearch");
      const visibleVideos = videoRows
        .map((title, index) => ({ title, index }))
        .filter((item) => matchesSearch([item.title], videoQuery));
      $("#videoList").innerHTML = visibleVideos.length ? visibleVideos.map(({ title, index }) => `
        <article class="row">
          <div class="thumb" aria-hidden="true"></div>
          <div><h3>${title}</h3><p>${english ? `Step-by-step service guide for ${selectCar}.` : `Пошаговая инструкция по обслуживанию ${selectCar}.`}</p></div>
          <div><p>${index < 2 ? (english ? "Today" : "Сегодня") : (english ? "May 2024" : "Май 2024")}</p><span class="tag">${index % 3 === 0 ? (english ? "Service" : "Обслуживание") : index % 3 === 1 ? t("hero.engine") : (english ? "Diagnostics" : "Диагностика")}</span></div>
        </article>
      `).join("") : emptyState(t("common.noMatches"));
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
      div.innerHTML = `${linkifyText(text)} <small>${new Date().toLocaleTimeString(currentLocale(), { hour: "2-digit", minute: "2-digit" })}</small>`;
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

    function currentLocale() {
      return getLanguage() === "en" ? "en-US" : "ru-RU";
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
          title: titleMatch ? titleMatch[1] : (isVideo ? (getLanguage() === "en" ? "Related video" : "Видео по теме") : (getLanguage() === "en" ? "Related link" : "Ссылка по теме")),
          source: forumMatch ? forumMatch[1] : (hostMatch ? hostMatch[1] : (getLanguage() === "en" ? "Material" : "Материал")),
          isVideo
        });
      }

      return links;
    }

    function normalizeResponseLinks(rawLinks) {
      if (!Array.isArray(rawLinks)) return [];
      const links = [];
      for (const item of rawLinks) {
        if (!item || typeof item !== "object") continue;
        const url = cleanUrl(item.url || item.link || "");
        if (!url || links.some((existing) => existing.url === url)) continue;
        const isVideo = /youtube\.com|youtu\.be|rutube\.ru|vimeo\.com/i.test(url) || item.type === "video";
        links.push({
          title: String(item.title || item.forum || item.name || item.source || (isVideo ? (getLanguage() === "en" ? "Related video" : "Видео по теме") : (getLanguage() === "en" ? "Related link" : "Ссылка по теме"))),
          url,
          source: String(item.source || item.forum || item.description || ""),
          description: String(item.description || item.key_info || ""),
          isVideo
        });
      }
      return links;
    }

    function updateTopicLinks(rawLinks) {
      const box = $("#topicLinks");
      if (!box) return;

      const links = Array.isArray(rawLinks) ? normalizeResponseLinks(rawLinks) : extractLinks(rawLinks);

      if (!links.length) {
        box.innerHTML = `<p>${t("assistant.linksFoundEmpty")}</p>`;
        return;
      }

      box.innerHTML = links.slice(0, 10).map((item) => `
        <div class="topic-link-item">
          <div class="topic-link-title">${item.isVideo ? (getLanguage() === "en" ? "Video: " : "Видео: ") : ""}${escapeHtml(item.title)}</div>
          <div>${escapeHtml(item.source)}</div>
          <a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.url)}</a>
        </div>
      `).join("");
    }

    const SERVICE_RECORDS_KEY = "puls_service_records_v1";

    function normalizeServiceRecord(record = {}, index = 0) {
      return {
        id: String(record.id || record.serviceId || `srv_${index}_${record.vehicleId || "record"}`).trim(),
        vehicleId: String(record.vehicleId || "").trim(),
        title: String(record.title || "").trim(),
        description: String(record.description || "").trim(),
        date: String(record.date || "").trim(),
        mileage: String(record.mileage || "").trim(),
        photoUrl: String(record.photoUrl || "").trim(),
        sticker: String(record.sticker || "🛠").trim(),
        color: String(record.color || "violet").trim(),
        status: String(record.status || "").trim()
      };
    }

    function createServiceRecordId() {
      return `srv_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    }

    function loadServiceRecords() {
      try {
        return JSON.parse(localStorage.getItem(SERVICE_RECORDS_KEY) || "[]")
          .filter(Boolean)
          .map((record, index) => normalizeServiceRecord(record, index));
      } catch (error) {
        return [];
      }
    }

    function saveServiceRecords(records) {
      try {
        const normalized = records
          .filter(Boolean)
          .map((record, index) => normalizeServiceRecord(record, index));
        localStorage.setItem(SERVICE_RECORDS_KEY, JSON.stringify(normalized.slice(0, 200)));
      } catch (error) {
        console.warn("Could not save service records:", error);
      }
    }

    function readServiceRecordsForVehicle(vehicleId) {
      const id = String(vehicleId || "").trim();
      return loadServiceRecords().filter((record) => String(record.vehicleId || "") === id);
    }

    function closeServiceRecordMenus(exceptId = "") {
      $$(".service[data-service-id]").forEach((item) => {
        if (exceptId && item.dataset.serviceId === exceptId) return;
        item.classList.remove("service-menu-open");
        const menu = item.querySelector(".service-menu");
        if (menu) menu.hidden = true;
        const button = item.querySelector("[data-service-menu-btn]");
        if (button) button.setAttribute("aria-expanded", "false");
      });
    }

    function toggleServiceRecordMenu(serviceId) {
      const item = $(`.service[data-service-id="${serviceId}"]`);
      if (!item) return;
      const isOpen = item.classList.toggle("service-menu-open");
      const menu = item.querySelector(".service-menu");
      if (menu) menu.hidden = !isOpen;
      const button = item.querySelector("[data-service-menu-btn]");
      if (button) button.setAttribute("aria-expanded", String(isOpen));
      closeServiceRecordMenus(isOpen ? serviceId : "");
    }

    function deleteServiceRecord(recordId) {
      const active = loadVehicleProfile();
      const nextRecords = loadServiceRecords().filter((record) => String(record.id || "") !== String(recordId || ""));
      saveServiceRecords(nextRecords);
      closeServiceRecordMenus();
      renderServiceRecords(active);
    }

    function openServiceModal() {
      const modal = $("#serviceModal");
      if (!modal) return;
      closeServiceRecordMenus();
      const form = $("#serviceForm");
      if (form) form.reset();
      const photoInput = $("#servicePhotoInput");
      if (photoInput) delete photoInput.dataset.previewUrl;
      const now = new Date();
      const dateInput = $("#serviceDateInput");
      if (dateInput) dateInput.value = now.toISOString().slice(0, 10);
      const status = $("#serviceFormStatus");
      if (status) status.textContent = "";
      updateServicePreview();
      modal.classList.add("show");
      modal.setAttribute("aria-hidden", "false");
    }

    function closeServiceModal() {
      const modal = $("#serviceModal");
      if (!modal) return;
      modal.classList.remove("show");
      modal.setAttribute("aria-hidden", "true");
    }

    async function fileToDataUrl(file) {
      if (!file) return "";
      return await new Promise((resolve) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ""));
        reader.onerror = () => resolve("");
        reader.readAsDataURL(file);
      });
    }

    function guessServiceSticker(text = "") {
      const source = String(text || "").toLowerCase();
      if (/(oil|масл)/.test(source)) return { sticker: "🛠", color: "violet" };
      if (/(brake|тормоз)/.test(source)) return { sticker: "🛞", color: "orange" };
      if (/(battery|аккум)/.test(source)) return { sticker: "🔋", color: "green" };
      if (/(air|filter|фильтр)/.test(source)) return { sticker: "◦", color: "cyan" };
      if (/(ac|a\/c|кондиц|freon|фреон)/.test(source)) return { sticker: "❄", color: "cyan" };
      return { sticker: "🛠", color: "violet" };
    }

    function updateServicePreview(photoUrl = "") {
      const preview = $("#servicePreview");
      if (!preview) return;
      const title = String($("#serviceTitleInput")?.value || "").trim();
      const description = String($("#serviceDescriptionInput")?.value || "").trim();
      const mergedText = `${title} ${description}`.trim();
      const { sticker, color } = guessServiceSticker(mergedText);
      const icon = preview.querySelector(".service-preview-icon");
      const titleNode = preview.querySelector("strong");
      const textNode = preview.querySelector("p");

      preview.classList.toggle("has-photo", Boolean(photoUrl));
      preview.style.backgroundImage = photoUrl ? `url("${photoUrl}")` : "";
      preview.dataset.color = color;
      if (icon) icon.textContent = photoUrl ? "📷" : sticker;
      if (titleNode) titleNode.textContent = title || t("service.previewTitle");
      if (textNode) {
        textNode.textContent = photoUrl
          ? (getLanguage() === "en" ? "Photo attached. The record will be saved with the picture." : "Фото прикреплено. Запись сохранится с изображением.")
          : (getLanguage() === "en" ? "You can add a photo or leave the colored sticker." : "Можно добавить фото или оставить цветной стикер.");
      }
    }

    async function saveServiceRecord(event) {
      event.preventDefault();
      if (!requireSignedInForEdit()) return;
      const active = loadVehicleProfile();
      const status = $("#serviceFormStatus");
      const title = String($("#serviceTitleInput")?.value || "").trim();
      const description = String($("#serviceDescriptionInput")?.value || "").trim();
      const date = String($("#serviceDateInput")?.value || "").trim();
      const mileage = String($("#serviceMileageInput")?.value || "").trim();
      const file = $("#servicePhotoInput")?.files?.[0] || null;

      if (!active?.id) {
        if (status) status.textContent = getLanguage() === "en" ? "Choose or create a car first." : "Сначала выберите или создайте автомобиль.";
        return;
      }
      if (!title || !date || !mileage) {
        if (status) status.textContent = getLanguage() === "en"
          ? "Please fill in title, date, and mileage."
          : "Заполните название, дату и пробег.";
        return;
      }

      const photoUrl = file ? await fileToDataUrl(file) : "";
      const { sticker, color } = guessServiceSticker(`${title} ${description}`);
      const record = {
        id: createServiceRecordId(),
        vehicleId: active.id,
        title,
        description,
        date,
        mileage,
        photoUrl,
        sticker,
        color,
        status: getLanguage() === "en" ? "Completed" : "Выполнено"
      };

      const records = loadServiceRecords();
      records.unshift(record);
      saveServiceRecords(records);
      if (status) status.textContent = t("service.saved");
      closeServiceModal();
      renderServiceRecords(active);
    }

    function renderVehicleSwitcher() {
      const box = $("#vehicleSwitcher");
      if (!box) return;
      const store = loadVehicleStore();
      const vehicles = store.vehicles;

      box.innerHTML = vehicles.map((vehicle) => {
        const isActive = vehicle.id === store.activeId;
        const label = getVehicleLabel(vehicle);
        const subtitle = [vehicle.year, vehicle.engine].filter(Boolean).join(" • ");
        return `
          <button type="button" class="vehicle-chip ${isActive ? "active" : ""}" data-vehicle-id="${escapeHtml(vehicle.id)}">
            <span>${escapeHtml(label)}</span>
            ${subtitle ? `<small>${escapeHtml(subtitle)}</small>` : ""}
          </button>
        `;
      }).join("") + `
        <button type="button" class="vehicle-chip vehicle-chip-add auth-required" id="vehicleAddChip">+ ${escapeHtml(t("car.addVehicle"))}</button>
      `;
    }

    function renderServiceRecords(vehicleProfile) {
      const serviceList = $("#serviceList");
      if (!serviceList) return;

      const english = getLanguage() === "en";
      const completedLabel = english ? "Completed" : "Выполнено";
      const fallbackRows = english ? [
        ["Engine oil and oil filter replacement", "Oil: 5W-30 Nissan Genuine Oil. Filter: original Nissan", "Today, 10:30", "98,500 km", "violet", "🛠"],
        ["Timing belt kit replacement", "Timing belt, rollers, tensioner, water pump. Manufacturer: Gates", "March 24, 2024", "90,120 km", "green", "⚙"],
        ["Air filter replacement", "Engine air filter. Manufacturer: Mann", "March 24, 2024", "90,120 km", "cyan", "◳"],
        ["Front brake pad replacement", "Front brake pads. Manufacturer: Brembo", "February 12, 2024", "86,780 km", "orange", "◎"],
        ["Fuel filter replacement", "Fuel filter. Manufacturer: Nissan", "November 10, 2023", "80,450 km", "violet", "◣"],
        ["A/C service", "Freon refill and leak check", "August 5, 2023", "74,230 km", "cyan", "❄"]
      ] : services;

      const activeRecords = readServiceRecordsForVehicle(vehicleProfile?.id);
      const userRows = activeRecords.map((record) => ({
        id: record.id,
        title: record.title || (english ? "Service record" : "Запись ТО"),
        description: record.description || "",
        date: record.date || "",
        mileage: record.mileage || "",
        color: record.color || "violet",
        sticker: record.photoUrl ? "" : (record.sticker || "🛠"),
        photoUrl: record.photoUrl || "",
        status: record.status || completedLabel
      }));

      const rows = userRows.length ? userRows : fallbackRows.map((item) => ({
        title: item[0],
        description: item[1],
        date: item[2],
        mileage: item[3],
        color: item[4] || "violet",
        sticker: item[5] || "🛠",
        photoUrl: "",
        status: completedLabel
      }));

      serviceList.innerHTML = rows.map((item) => {
        const mediaStyle = item.photoUrl ? `style="background-image:url('${escapeHtml(item.photoUrl)}')"` : "";
        const mediaClass = item.photoUrl ? "has-photo" : `service-media-${item.color || "violet"}`;
        const mediaContent = item.photoUrl ? "" : `<small>${escapeHtml(item.sticker || "🛠")}</small>`;
        const menuMarkup = item.id ? `
          <div class="service-actions">
            <button type="button" class="service-menu-btn" data-service-menu-btn data-service-id="${escapeHtml(item.id)}" aria-haspopup="menu" aria-expanded="false" aria-label="Меню записи">⋯</button>
            <div class="service-menu" data-service-menu="${escapeHtml(item.id)}" hidden>
              <button type="button" class="service-menu-delete" data-service-delete="${escapeHtml(item.id)}">✕ ${escapeHtml(getLanguage() === "en" ? "Delete record" : "Удалить запись")}</button>
            </div>
          </div>` : "";
        return `
          <article class="service" data-service-id="${escapeHtml(item.id || "")}">
            <div class="service-media ${mediaClass}" ${mediaStyle}>${mediaContent}</div>
            <div>
              <h3>${escapeHtml(item.title)}</h3>
              <p>${escapeHtml(item.description)}</p>
              <p class="ok">${escapeHtml(item.status)}</p>
            </div>
            <div><p>${escapeHtml(item.date)}</p><p>${escapeHtml(english ? "Mileage" : "Пробег")}: ${escapeHtml(item.mileage)}</p></div>
            ${menuMarkup}
          </article>
        `;
      }).join("");

      closeServiceRecordMenus();
    }

    const HISTORY_STORAGE_KEY = "puls_request_history_v2";

    function loadLocalHistory() {
      try {
        return JSON.parse(localStorage.getItem(HISTORY_STORAGE_KEY) || "[]");
      } catch (error) {
        return [];
      }
    }

    async function loadUserHistory() {
      const appUser = window.pulsAppUser;
      if (!window.supabaseClient || !appUser?.id) return [];

      const { data, error } = await window.supabaseClient
        .from("diagnostic_requests")
        .select("id,question,answer,language,request_type,status,created_at,vehicle_id")
        .eq("user_id", appUser.id)
        .order("created_at", { ascending: false })
        .limit(100);

      if (error) {
        console.warn("Не удалось загрузить diagnostic_requests:", error.message);
        return loadLocalHistory();
      }

      return (data || []).map((row) => {
        const createdAt = row.created_at ? new Date(row.created_at) : new Date();
        return {
          id: row.id,
          question: row.question,
          answer: row.answer || "",
          links: extractLinks(row.answer || ""),
          date: createdAt.toLocaleDateString(currentLocale(), { day: "2-digit", month: "short" }) + ", " +
            createdAt.toLocaleTimeString(currentLocale(), { hour: "2-digit", minute: "2-digit" }),
          vehicle: `${t("hero.car")} • ${t("hero.engineValue")} • ${t("hero.driveValue")}`,
          type: row.request_type === "voice"
            ? (getLanguage() === "en" ? "Voice request" : "Голосовой запрос")
            : (getLanguage() === "en" ? "Text request" : "Текстовый запрос"),
          status: row.status || "new"
        };
      });
    }

    async function saveHistoryItem(question, answer, links = []) {
      const item = {
        question,
        answer,
        links,
        vehicle: `${t("hero.car")} • ${t("hero.engineValue")} • ${t("hero.driveValue")}`,
        type: getLanguage() === "en" ? "Text request" : "Текстовый запрос"
      };

      const now = new Date();
      const localItem = {
        ...item,
        date: now.toLocaleDateString(currentLocale(), { day: "2-digit", month: "short" }) + ", " + now.toLocaleTimeString(currentLocale(), { hour: "2-digit", minute: "2-digit" })
      };

      const appUser = window.pulsAppUser;
      if (window.supabaseClient && appUser?.id) {
        const { error } = await window.supabaseClient
          .from("diagnostic_requests")
          .insert({
            user_id: appUser.id,
            question,
            answer,
            language: getLanguage(),
            request_type: "text",
            status: "new",
            source: "web"
          });

        if (error) {
          console.warn("Не удалось сохранить diagnostic_requests:", error.message);
        }
      }

      const history = loadLocalHistory();
      history.unshift(localItem);
      localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(history.slice(0, 50)));
      await renderLists();
    }

    function updateQuota(quota) {
      if (!quota) return;
      const pill = $(".system-pill");
      if (!pill) return;

      if (quota.unlimited) {
        pill.textContent = t("system.premium");
      } else {
        pill.textContent = t("system.freeQuota", { remaining: quota.remaining, limit: quota.limit });
      }
    }

    function updateKeyChecks(answer) {
      const box = $("#keyChecks");
      if (!box) return;
      const lines = String(answer)
        .split(/\n|•|-|\d+[.)]/)
        .map((line) => line.trim())
        .filter(Boolean);
      const important = lines.filter((line) => /проверь|проверить|начни|датчик|ремень|ролик|генератор|масло|ошиб|check|inspect|start|sensor|belt|pulley|alternator|oil|error|obd|spark|coil|pump|pressure|egr|turbo|filter/i.test(line)).slice(0, 5);
      const finalLines = important.length ? important : lines.slice(0, 4);
      box.innerHTML = finalLines.length
        ? `<ul style="margin:8px 0 0; padding-left:20px; color:var(--soft); line-height:1.6">${finalLines.map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ul>`
        : `<p>${t("assistant.checksEmpty")}</p>`;
    }

    async function getCurrentAuthUser() {
      if (!window.supabaseClient) return null;
      const { data, error } = await window.supabaseClient.auth.getUser();
      return error ? null : data.user;
    }

    async function sendPrompt() {
      const input = $("#promptInput");
      const prompt = input.value.trim();
      if (!prompt) return;
      showView("assistant");

      const user = await getCurrentAuthUser();
      if (!user) {
        toast(t("assistant.authRequired"));
        window.openAuthModal?.();
        return;
      }

      const appUser = window.pulsAppUser || await window.syncAuthUserProfile?.(user);
      if (!appUser || appUser.auth_user_id !== user.id) {
        toast(t("assistant.authRequired"));
        return;
      }

      window.pulsAppUser = appUser;

      appendMessage(prompt, true);
      input.value = "";

      const loading = appendMessage(t("assistant.loading"), false);
      try {
        const res = await fetch(CHAT_API_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: prompt,
            source: "web",
            auth_user_id: user.id,
            username: user.email || "web_user",
            first_name: user.user_metadata?.full_name || "Web",
            email: user.email,
            language: getLanguage(),
            car_info: appUser.car_info || "",
            conversation_history: appUser.conversation_history || "",
            telegram_id: appUser.telegram_id || "",
            chat_id: appUser.telegram_id || ""
          })
        });

        if (!res.ok) {
          const errorBody = await res.text().catch(() => "");
          throw new Error(`Chat API returned ${res.status}: ${errorBody || res.statusText}`);
        }

        const rawAnswer = await res.text();
        let data;
        try {
          data = JSON.parse(rawAnswer);
        } catch (error) {
          data = { answer: rawAnswer };
        }

        const answer = data.answer || data.reply || data.message || data.output || rawAnswer || JSON.stringify(data, null, 2);
        const links = normalizeResponseLinks(data.links || []);
        loading.innerHTML = `<strong>PULS</strong><br>${linkifyText(answer)} <small>${new Date().toLocaleTimeString(currentLocale(), { hour: "2-digit", minute: "2-digit" })}</small>`;
        updateKeyChecks(answer);
        updateTopicLinks(links.length ? links : answer);
        updateQuota(data.quota);
        await saveHistoryItem(prompt, answer, links);
        await renderLists();
        scrollMessagesToBottom();
      } catch (error) {
        console.error("PULS /chat request failed:", error);
        const errorText = t("assistant.error");
        loading.innerHTML = `<strong>PULS</strong><br>${errorText} <small>${new Date().toLocaleTimeString(currentLocale(), { hour: "2-digit", minute: "2-digit" })}</small>`;
        updateKeyChecks(errorText);
        await saveHistoryItem(prompt, errorText, []);
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
      applyLanguage();
      initVehicleEditor();
      await renderLists();
      connectSpline();

      $("#sendBtn").addEventListener("click", sendPrompt);
      $("#promptInput").addEventListener("keydown", (event) => {
        if (event.key === "Enter") sendPrompt();
      });
      ["#journalSearch", "#historySearch", "#manualSearch", "#videoSearch"].forEach((selector) => {
        $(selector)?.addEventListener("input", () => renderLists());
      });
      $("#carPhotoInput")?.addEventListener("change", (event) => {
        updateCarPhoto(event.target.files?.[0]);
      });
      $("#serviceForm")?.addEventListener("submit", saveServiceRecord);
      ["#serviceTitleInput", "#serviceDescriptionInput", "#serviceDateInput", "#serviceMileageInput"].forEach((selector) => {
        $(selector)?.addEventListener("input", () => updateServicePreview($("#servicePhotoInput")?.dataset.previewUrl || ""));
      });
      $("#servicePhotoInput")?.addEventListener("change", async (event) => {
        const file = event.target.files?.[0] || null;
        const photoUrl = file ? await fileToDataUrl(file) : "";
        event.target.dataset.previewUrl = photoUrl;
        updateServicePreview(photoUrl);
      });
      $("#languageSelect")?.addEventListener("change", (event) => {
        setLanguage(event.target.value);
      });
      window.addEventListener("puls-auth-change", () => {
        applyAuthLockedState();
        renderLists();
      });
      applyAuthLockedState();
      window.addEventListener("resize", syncAssistantMessageHeight);
      syncAssistantMessageHeight();
      document.addEventListener("click", (event) => {
        if (event.target.closest("#requestCloseBtn") || event.target.closest("#requestModal") && event.target.id === "requestModal") {
          closeRequestModal();
          return;
        }

        if (openRequestByClick(event.target)) {
          return;
        }

        if (guardAuthAction(event.target)) {
          event.preventDefault();
          return;
        }

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

        const toggleButton = event.target.closest(".toggle-switch[data-toggle]");
        if (toggleButton) {
          const active = !toggleButton.classList.contains("active");
          toggleButton.classList.toggle("active", active);
          toggleButton.setAttribute("aria-pressed", String(active));
          return;
        }

        const addVehicleButton = event.target.closest("#addVehicleBtn, #vehicleAddChip");
        if (addVehicleButton) {
          const vehicle = addVehicleProfile();
          fillVehicleForm(vehicle);
          renderLists();
          showView("car");
          return;
        }

        const deleteVehicleButton = event.target.closest("#deleteVehicleBtn");
        if (deleteVehicleButton) {
          const store = loadVehicleStore();
          const activeVehicle = store.vehicles.find((vehicle) => vehicle.id === store.activeId) || store.vehicles[0];
          const label = getVehicleLabel(activeVehicle);
          const confirmed = window.confirm(`${t("car.deleteVehicle")}: ${label}?`);
          if (!confirmed) return;
          const nextVehicle = removeActiveVehicleProfile();
          fillVehicleForm(nextVehicle);
          renderLists();
          showView("car");
          return;
        }

        const vehicleChip = event.target.closest("[data-vehicle-id]");
        if (vehicleChip) {
          const active = setActiveVehicleProfile(vehicleChip.dataset.vehicleId);
          fillVehicleForm(active);
          renderLists();
          return;
        }

        const serviceButton = event.target.closest("#serviceAddBtn");
        if (serviceButton) {
          openServiceModal();
          return;
        }

        const serviceMenuButton = event.target.closest("[data-service-menu-btn]");
        if (serviceMenuButton) {
          toggleServiceRecordMenu(serviceMenuButton.dataset.serviceId);
          return;
        }

        const serviceDeleteButton = event.target.closest("[data-service-delete]");
        if (serviceDeleteButton) {
          deleteServiceRecord(serviceDeleteButton.dataset.serviceDelete);
          return;
        }

        const serviceClose = event.target.closest("#serviceCloseBtn, #serviceCancelBtn");
        if (serviceClose) {
          closeServiceModal();
          return;
        }

        if (event.target.id === "serviceModal") {
          closeServiceModal();
          return;
        }

        if (!event.target.closest(".service-actions")) {
          closeServiceRecordMenus();
        }

        const infoButton = event.target.closest(".info-btn[data-info]");
        if (infoButton) {
          toggleHelp(infoButton.dataset.info);
          return;
        }

        const action = event.target.closest("[data-action]")?.dataset.action;
        if (!action) return;
        $("#composerMenu")?.classList.remove("show");
        $("#composerMenuBtn")?.setAttribute("aria-expanded", "false");
        if (event.target.closest("#composerMenuBtn")) return;
        if (action === "filter") {
          renderLists();
        } else if (action === "pay") {
          toast(t("toast.pay"));
        } else if (action === "dtc") {
          showView("dtc");
          toast(t("toast.dtc"));
        } else if (action === "voice") {
          toast(t("toast.voice"));
        } else {
          toast(t("toast.demo"));
        }
      });

      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
          closeRequestModal();
        }

        const requestRow = event.target.closest("[data-request-kind][data-request-index]");
        if (requestRow && (event.key === "Enter" || event.key === " ")) {
          event.preventDefault();
          openRequestByClick(event.target);
        }
      });
    });
