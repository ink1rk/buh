/* JARVIS Web UI.
 *
 * Ни сборки, ни фреймворка: интерфейс целиком живёт на Core API, который уже
 * используют бот и tg-user. Второго источника правды здесь нет — экран только
 * показывает то, что отдаёт ядро, и отправляет обратно решения владельца.
 */

const TOKEN_KEY = 'jarvis_token';
const THEME_KEY = 'jarvis_theme';

/* --- доступ к ядру ------------------------------------------------------ */
const token = {
    get: () => localStorage.getItem(TOKEN_KEY) || '',
    set: (value) => localStorage.setItem(TOKEN_KEY, value),
    clear: () => localStorage.removeItem(TOKEN_KEY),
};

class Unauthorized extends Error { }

async function call(path, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (options.body !== undefined) headers['Content-Type'] = 'application/json';
    const secret = token.get();
    if (secret) headers['X-Assistant-Token'] = secret;

    const response = await fetch(path, {
        ...options,
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
    if (response.status === 401) throw new Unauthorized('нужен токен');
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
}

const api = {
    get: (path) => call('/api' + path),
    post: (path, body) => call('/api' + path, { method: 'POST', body: body || {} }),
    patch: (path, body) => call('/api' + path, { method: 'PATCH', body }),
    del: (path) => call('/api' + path, { method: 'DELETE' }),
    legacy: (path) => call(path),
};

/* --- вывод -------------------------------------------------------------- */
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
));

const plural = (n, one, few, many) => {
    const mod100 = n % 100;
    const mod10 = n % 10;
    if (mod100 >= 11 && mod100 <= 14) return many;
    if (mod10 === 1) return one;
    if (mod10 >= 2 && mod10 <= 4) return few;
    return many;
};

function ago(seconds) {
    if (!seconds) return '';
    const diff = Date.now() / 1000 - seconds;
    if (diff < 60) return 'только что';
    if (diff < 3600) {
        const m = Math.floor(diff / 60);
        return `${m} ${plural(m, 'минуту', 'минуты', 'минут')} назад`;
    }
    if (diff < 86400) {
        const h = Math.floor(diff / 3600);
        return `${h} ${plural(h, 'час', 'часа', 'часов')} назад`;
    }
    const d = Math.floor(diff / 86400);
    if (d < 30) return `${d} ${plural(d, 'день', 'дня', 'дней')} назад`;
    return stamp(seconds, { day: 'numeric', month: 'short' });
}

/* Ошибка действия несёт имя класса исключения — это для журнала, не для человека. */
function plainError(error, fallback) {
    const text = (error || '').replace(/^[A-Za-z_]*Error:\s*/, '').trim();
    return text || fallback;
}

function stamp(seconds, options) {
    if (!seconds) return '';
    return new Date(seconds * 1000).toLocaleString('ru-RU',
        options || { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

const clock = (seconds) => seconds
    ? new Date(seconds * 1000).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
    : '';

const empty = (text) => `<div class="empty">${esc(text)}</div>`;

/* Модель иногда отвечает телеграмным HTML — оставляем только разметку текста. */
function rich(value) {
    const safe = esc(value);
    return safe
        .replace(/&lt;(\/?)(b|strong|i|em|u|code)&gt;/g, '<$1$2>')
        .replace(/&lt;br\s*\/?&gt;/g, '<br>');
}

/* --- состояние ---------------------------------------------------------- */
const state = {
    overview: null,
    security: null,
    chat: [],
};

/* --- навигация ---------------------------------------------------------- */
const NAV = [
    {
        title: 'Главное', items: [
            { path: '', label: 'Сегодня' },
            { path: 'chat', label: 'Чат' },
            { path: 'inbox', label: 'Входящие', badge: 'inbox' },
            { path: 'calendar', label: 'Расписание' },
        ]
    },
    {
        title: 'Знание', items: [
            { path: 'memory', label: 'Память' },
            { path: 'contacts', label: 'Люди' },
            { path: 'conversations', label: 'Диалоги' },
        ]
    },
    {
        title: 'Мир', items: [
            { path: 'news', label: 'Новости' },
        ]
    },
    {
        title: 'Система', items: [
            { path: 'activity', label: 'Активность' },
            { path: 'actions', label: 'Действия', badge: 'approvals' },
            { path: 'integrations', label: 'Интеграции' },
            { path: 'notifications', label: 'Уведомления' },
            { path: 'settings', label: 'Настройки' },
        ]
    },
];

function badgeCount(kind) {
    const attention = state.overview?.attention;
    if (!attention) return 0;
    if (kind === 'inbox') return attention.suggestions + attention.i_owe + attention.waiting;
    if (kind === 'approvals') return attention.approvals;
    return 0;
}

function sidebar(active) {
    const groups = NAV.map((group) => `
        <div class="nav-group nav">
            <div class="nav-title">${esc(group.title)}</div>
            ${group.items.map((item) => {
        const on = item.path === active ? ' on' : '';
        const count = item.badge ? badgeCount(item.badge) : 0;
        const badge = count ? `<span class="count">${count}</span>` : '';
        return `<a class="${on.trim()}" href="#/${item.path}">
                            <span>${esc(item.label)}</span>${badge}
                        </a>`;
    }).join('')}
        </div>`).join('');

    return `<aside class="sidebar">
        <div class="brand"><b>${esc(state.overview?.assistant || 'JARVIS')}</b><span>panel</span></div>
        ${groups}
        <div class="sidebar-foot">
            <button class="btn ghost" data-theme-toggle>Сменить тему</button>
        </div>
    </aside>`;
}

/* --- страницы ----------------------------------------------------------- */
const pages = {};

pages[''] = {
    title: 'Сегодня',
    async render() {
        const [data, calendar] = await Promise.all([
            api.get('/overview'), api.get('/calendar'),
        ]);
        state.overview = data;
        const a = data.attention;
        const date = new Date(data.now).toLocaleDateString('ru-RU',
            { weekday: 'long', day: 'numeric', month: 'long' });

        const tile = (href, n, label, tone) =>
            `<a class="stat ${n ? (tone || '') : 'quiet'}" href="${href}">
                <div class="n">${n}</div><div class="k">${esc(label)}</div>
            </a>`;

        const suggestions = data.suggestions.length ? data.suggestions.map((s) => `
            <a class="row" href="#/inbox">
                <div class="grow">
                    <div class="title">${esc(s.contact_name)}
                        ${s.channel === 'email' ? '<span class="badge">письмо</span>' : ''}</div>
                    <div class="sub clip">${esc(s.subject || s.context_summary || s.options[0] || '')}</div>
                </div>
                <div class="when">${ago(s.created_at)}</div>
            </a>`).join('') : empty('Новых сообщений нет');

        const commitment = (c, arrow) => `
            <div class="row">
                <div class="grow">
                    <div class="title">${arrow} ${esc(c.description)}</div>
                    <div class="sub">${esc(c.counterparty_name || 'без контакта')}${c.due_at ? ' · до ' + stamp(c.due_at) : ''}</div>
                </div>
                ${c.status === 'OVERDUE' ? '<span class="badge bad">просрочено</span>' : ''}
            </div>`;

        const mine = data.i_owe.length
            ? data.i_owe.map((c) => commitment(c, '→')).join('')
            : empty('Ничего не обещано');
        const theirs = data.waiting.length
            ? data.waiting.map((c) => commitment(c, '←')).join('')
            : empty('Никого не ждём');

        const system = data.system.integrations.map((i) => {
            const tone = i.status === 'CONNECTED' ? 'ok' : i.status === 'ERROR' ? 'bad' : 'warn';
            return `<div class="row">
                <span class="badge ${tone}"><span class="dot"></span></span>
                <div class="grow"><div class="title">${esc(i.name)}</div>
                    <div class="sub clip">${esc(i.detail || '')}</div></div>
                <div class="when">${esc(i.status.toLowerCase())}</div>
            </div>`;
        }).join('');

        return `
            <div class="page-head">
                <h1>${esc(data.greeting)}${data.owner ? ', ' + esc(data.owner) : ''}</h1>
                <p class="lede">${esc(date)}</p>
            </div>
            ${securityNotice()}

            <h2>Требует внимания</h2>
            <div class="grid cols-4">
                ${tile('#/inbox', a.suggestions, 'ждут ответа', 'alert')}
                ${tile('#/actions', a.approvals, 'на подтверждение', 'alert')}
                ${tile('#/inbox', a.i_owe, 'я обещал')}
                ${tile('#/inbox', a.waiting, 'жду от других')}
            </div>

            ${calendar.enabled ? `<h2>Сегодня в календаре</h2>
            <div class="list">${calendar.today.length
                ? calendar.today.map(eventRow).join('')
                : empty('Встреч на сегодня нет')}</div>` : ''}

            <h2>Новые сообщения</h2>
            <div class="list">${suggestions}</div>

            <h2>Я обещал</h2>
            <div class="list">${mine}</div>

            <h2>Жду ответа</h2>
            <div class="list">${theirs}</div>

            <h2>Система</h2>
            <div class="list">${system}</div>`;
    },
};

pages.chat = {
    title: 'Чат',
    async render() {
        const history = state.chat.map((m) => `
            <div class="msg ${m.me ? 'me' : ''}">
                <div class="who">${esc(m.me ? 'Я' : (m.agent || 'Джарвис'))}</div>
                <div>${rich(m.text)}</div>
            </div>`).join('');

        return `
            <div class="page-head"><h1>Чат</h1>
                <p class="lede">Тот же конвейер, что у Telegram: контекст, намерение, агент.</p></div>
            <div class="chat" id="chat">${history || empty('Спроси что-нибудь')}</div>
            <form class="composer" id="say">
                <textarea id="text" rows="1" placeholder="Что у меня сегодня?"></textarea>
                <button class="btn primary" type="submit">Отправить</button>
            </form>`;
    },
    mount(root) {
        const form = root.querySelector('#say');
        const input = root.querySelector('#text');
        const log = root.querySelector('#chat');
        input.focus();
        log.scrollTop = log.scrollHeight;

        form.addEventListener('submit', async (event) => {
            event.preventDefault();
            const text = input.value.trim();
            if (!text) return;
            state.chat.push({ me: true, text });
            input.value = '';
            input.disabled = true;
            render();

            try {
                const answer = await api.post('/chat', { text, session: 'web', interface: 'web' });
                state.chat.push({ me: false, text: answer.reply || '(пусто)', agent: answer.agent });
            } catch (error) {
                if (error instanceof Unauthorized) throw error;
                state.chat.push({ me: false, text: 'Ядро не ответило: ' + error.message });
            }
            render();
        });
    },
};

pages.inbox = {
    title: 'Входящие',
    async render() {
        const [suggestions, commitments] = await Promise.all([
            api.get('/suggestions?status=NEW&limit=30'),
            api.get('/commitments?status=OPEN&limit=50'),
        ]);

        const cards = suggestions.suggestions.length
            ? suggestions.suggestions.map((s) => `
                <div class="card" style="margin-bottom:12px" data-suggestion="${esc(s.id)}">
                    <div class="bar" style="margin-bottom:8px">
                        <div class="grow">
                            <h3>${esc(s.contact_name)}
                                ${s.channel === 'email' ? '<span class="badge">письмо</span>' : ''}</h3>
                            ${s.subject ? `<div class="title">${esc(s.subject)}</div>` : ''}
                            <div class="muted">${esc(s.context_summary || '')}</div></div>
                        <div class="when">${ago(s.created_at)}</div>
                    </div>
                    <div class="actions" style="margin:12px 0">
                        ${s.options.map((option, index) => `
                            <button class="btn" data-send="${index}">${esc(option)}</button>`).join('')}
                    </div>
                    <div class="bar" style="margin:0">
                        <input class="grow" type="text" data-own placeholder="Написать свой ответ">
                        <button class="btn primary" data-send-own>Отправить</button>
                        <button class="btn ghost" data-ignore>Пропустить</button>
                        ${s.channel === 'email' ? `<button class="btn ghost"
                            data-mute="${esc(s.peer_id)}">Это робот</button>` : ''}
                    </div>
                    <div class="muted" data-result style="margin-top:8px"></div>
                </div>`).join('')
            : `<div class="list">${empty('Новых сообщений нет')}</div>`;

        const mine = commitments.commitments.filter((c) => c.direction === 'I_OWE');
        const theirs = commitments.commitments.filter((c) => c.direction === 'THEY_OWE');

        const rows = (items, arrow, none) => items.length ? items.map((c) => `
            <div class="row">
                <div class="grow">
                    <div class="title">${arrow} ${esc(c.description)}</div>
                    <div class="sub">${esc(c.counterparty_name || 'без контакта')}${c.due_at ? ' · до ' + stamp(c.due_at) : ''}</div>
                </div>
                ${c.status === 'OVERDUE' ? '<span class="badge bad">просрочено</span>' : ''}
                <div class="actions">
                    <button class="btn ghost" data-done="${esc(c.id)}">Выполнено</button>
                    <button class="btn ghost danger" data-drop="${esc(c.id)}">Снять</button>
                </div>
            </div>`).join('') : empty(none);

        return `
            <div class="page-head"><h1>Входящие</h1>
                <p class="lede">Кто написал, что я обещал и кого жду.</p></div>
            <h2>Ждут ответа</h2>
            ${cards}
            <h2>Я обещал</h2>
            <div class="list">${rows(mine, '→', 'Ничего не обещано')}</div>
            <h2>Жду ответа</h2>
            <div class="list">${rows(theirs, '←', 'Никого не ждём')}</div>`;
    },
    mount(root) {
        root.querySelectorAll('[data-suggestion]').forEach((card) => {
            const id = card.dataset.suggestion;
            const result = card.querySelector('[data-result]');

            const send = async (body) => {
                card.querySelectorAll('button').forEach((b) => { b.disabled = true; });
                result.textContent = 'Отправляю…';
                try {
                    const answer = await api.post(`/suggestions/${id}/send`, body);
                    result.textContent = answer.status === 'SUCCESS'
                        ? 'Отправлено.'
                        : `Не отправлено: ${answer.error || answer.status}`;
                    if (answer.status === 'SUCCESS') setTimeout(render, 700);
                } catch (error) {
                    if (error instanceof Unauthorized) throw error;
                    result.textContent = 'Ошибка: ' + error.message;
                    card.querySelectorAll('button').forEach((b) => { b.disabled = false; });
                }
            };

            card.querySelectorAll('[data-send]').forEach((button) => {
                button.addEventListener('click', () => send({ index: Number(button.dataset.send) }));
            });
            card.querySelector('[data-send-own]').addEventListener('click', () => {
                const text = card.querySelector('[data-own]').value.trim();
                if (text) send({ text });
            });
            card.querySelector('[data-ignore]').addEventListener('click', async () => {
                await api.post(`/suggestions/${id}/ignore`);
                render();
            });
            card.querySelector('[data-mute]')?.addEventListener('click', async (event) => {
                await api.post('/mail/sender',
                    { address: event.target.dataset.mute, robot: true });
                await api.post(`/suggestions/${id}/ignore`);
                render();
            });
        });

        root.querySelectorAll('[data-done]').forEach((button) => {
            button.addEventListener('click', async () => {
                await api.patch(`/commitments/${button.dataset.done}`, { status: 'DONE' });
                render();
            });
        });
        root.querySelectorAll('[data-drop]').forEach((button) => {
            button.addEventListener('click', async () => {
                await api.patch(`/commitments/${button.dataset.drop}`, { status: 'CANCELLED' });
                render();
            });
        });
    },
};

const MEMORY_TYPES = ['FACT', 'PREFERENCE', 'EVENT', 'RELATION', 'PROCEDURE', 'EPISODE'];
const SOURCE_LABEL = {
    USER_EXPLICIT: 'сказано напрямую',
    USER_MESSAGE: 'из сообщения владельца',
    TELEGRAM: 'из переписки в Telegram',
    EMAIL: 'из почты',
    CALENDAR: 'из календаря',
    TOOL_RESULT: 'из результата инструмента',
    LLM_INFERENCE: 'вывод модели, не факт',
};

pages.memory = {
    title: 'Память',
    async render(params) {
        const type = params.get('type') || '';
        const query = params.get('q') || '';

        let items;
        if (query) {
            const found = await api.post('/memory/search', { query, limit: 50 });
            items = found.results.filter((m) => !type || m.type === type);
        } else {
            const path = '/memory?limit=200' + (type ? `&type=${encodeURIComponent(type)}` : '');
            items = (await api.get(path)).memories;
        }

        const chips = ['', ...MEMORY_TYPES].map((value) => `
            <button class="chip ${value === type ? 'on' : ''}" data-type="${value}">
                ${esc(value || 'Все')}</button>`).join('');

        const rows = items.length ? items.map((m) => `
            <div class="row" data-memory="${esc(m.id)}">
                <div class="grow">
                    <div class="title" data-content>${esc(m.content)}</div>
                    <div class="sub">
                        <span class="badge">${esc(m.type.toLowerCase())}</span>
                        <span class="${m.source === 'LLM_INFERENCE' ? 'badge warn' : 'badge'}">${esc(SOURCE_LABEL[m.source] || m.source)}</span>
                        · уверенность ${Math.round(m.confidence * 100)}%
                        · важность ${Math.round(m.importance * 100)}%
                        · ${esc(stamp(m.created_at))}
                        ${m.status !== 'ACTIVE' ? ' · <b>' + esc(m.status.toLowerCase()) + '</b>' : ''}
                    </div>
                </div>
                <div class="actions">
                    <button class="btn ghost" data-edit>Правка</button>
                    <button class="btn ghost" data-archive>В архив</button>
                    <button class="btn ghost danger" data-delete>Удалить</button>
                </div>
            </div>`).join('') : empty(query ? 'Ничего не нашлось' : 'Память пуста');

        return `
            <div class="page-head"><h1>Память</h1>
                <p class="lede">Что JARVIS знает и откуда — источник виден у каждой записи.</p></div>
            <div class="bar">
                <input class="grow" type="search" id="q" value="${esc(query)}"
                       placeholder="Поиск по памяти">
            </div>
            <div class="chips" style="margin-bottom:16px">${chips}</div>
            <div class="list">${rows}</div>`;
    },
    mount(root, params) {
        const search = root.querySelector('#q');
        search.addEventListener('keydown', (event) => {
            if (event.key !== 'Enter') return;
            const next = new URLSearchParams(params);
            if (search.value.trim()) next.set('q', search.value.trim());
            else next.delete('q');
            go('memory', next);
        });

        root.querySelectorAll('[data-type]').forEach((chip) => {
            chip.addEventListener('click', () => {
                const next = new URLSearchParams(params);
                if (chip.dataset.type) next.set('type', chip.dataset.type);
                else next.delete('type');
                go('memory', next);
            });
        });

        root.querySelectorAll('[data-memory]').forEach((row) => {
            const id = row.dataset.memory;
            row.querySelector('[data-delete]').addEventListener('click', async () => {
                if (!confirm('Удалить запись насовсем?')) return;
                await api.del(`/memory/${id}`);
                render();
            });
            row.querySelector('[data-archive]').addEventListener('click', async () => {
                await api.patch(`/memory/${id}`, { status: 'ARCHIVED' });
                render();
            });
            row.querySelector('[data-edit]').addEventListener('click', async () => {
                const current = row.querySelector('[data-content]').textContent.trim();
                const next = prompt('Изменить запись:', current);
                if (next === null || next.trim() === current) return;
                await api.patch(`/memory/${id}`, { content: next.trim() });
                render();
            });
        });
    },
};

pages.contacts = {
    title: 'Люди',
    async render(params) {
        const id = params.get('id');
        if (id) return contactCard(id);

        const { contacts } = await api.get('/contacts');
        const rows = contacts.length ? contacts.map((c) => `
            <a class="row" href="#/contacts?id=${encodeURIComponent(c.id)}">
                <div class="grow">
                    <div class="title">${esc(c.display_name)}${c.is_owner ? ' <span class="badge accent">владелец</span>' : ''}</div>
                    <div class="sub clip">${esc((c.aliases || []).join(', ') || 'без псевдонимов')}</div>
                </div>
                <span class="badge">${esc((c.relationship_type || 'unknown').toLowerCase())}</span>
                <div class="when">${c.last_interaction_at ? ago(c.last_interaction_at) : ''}</div>
            </a>`).join('') : empty('Контактов пока нет');

        return `
            <div class="page-head"><h1>Люди</h1>
                <p class="lede">Кто есть кто, как общаемся и что осталось открытым.</p></div>
            <div class="list">${rows}</div>`;
    },
    mount(root) {
        const remove = root.querySelector('[data-delete-contact]');
        if (!remove) return;
        remove.addEventListener('click', async () => {
            if (!confirm('Удалить контакт вместе с памятью, диалогами и обязательствами?')) return;
            await api.del(`/contacts/${remove.dataset.deleteContact}`);
            go('contacts', new URLSearchParams());
        });
    },
};

async function contactCard(id) {
    const data = await api.get(`/contacts/${encodeURIComponent(id)}/context`);
    if (data.error) return empty('Контакт не найден');
    const c = data.contact;
    const style = c.communication_style || {};

    const field = (label, value) => value
        ? `<div class="row"><div class="grow"><div class="sub">${esc(label)}</div>
               <div class="title">${esc(value)}</div></div></div>`
        : '';

    const commitments = data.commitments.length ? data.commitments.map((item) => `
        <div class="row"><div class="grow">
            <div class="title">${item.direction === 'I_OWE' ? '→' : '←'} ${esc(item.description)}</div>
            <div class="sub">${item.due_at ? 'до ' + esc(stamp(item.due_at)) : 'без срока'}</div>
        </div></div>`).join('') : empty('Открытых обязательств нет');

    const memories = data.memories.length ? data.memories.map((m) => `
        <div class="row"><div class="grow">
            <div class="title">${esc(m.content)}</div>
            <div class="sub">${esc(m.type.toLowerCase())} · ${esc(SOURCE_LABEL[m.source] || m.source)} · ${esc(stamp(m.created_at))}</div>
        </div></div>`).join('') : empty('Пока ничего не запомнено');

    const conversations = data.conversations.length ? data.conversations.map((item) => `
        <a class="row" href="#/conversations?id=${encodeURIComponent(item.id)}">
            <div class="grow"><div class="title">${esc(item.title || item.platform)}</div>
                <div class="sub clip">${esc(item.summary || 'без резюме')}</div></div>
            <div class="when">${ago(item.last_message_at)}</div>
        </a>`).join('') : empty('Диалогов нет');

    return `
        <div class="page-head">
            <a class="muted" href="#/contacts">← Люди</a>
            <h1 style="margin-top:8px">${esc(c.display_name)}</h1>
            <p class="lede">${esc((c.relationship_type || 'unknown').toLowerCase())}${c.relationship_source === 'LLM_INFERENCE' ? ' · предположение' : ''}</p>
        </div>
        <h2>Карточка</h2>
        <div class="list">
            ${field('Псевдонимы', (c.aliases || []).join(', '))}
            ${field('Telegram', (c.telegram_ids || []).join(', '))}
            ${field('Почта', (c.emails || []).join(', '))}
            ${field('Телефон', (c.phones || []).join(', '))}
            ${field('Последний контакт', c.last_interaction_at ? stamp(c.last_interaction_at) : '')}
            ${field('Стиль общения', [style.length, style.formality, style.emoji && 'эмодзи ' + style.emoji]
            .filter(Boolean).join(', '))}
            ${field('Заметки', c.notes)}
        </div>
        <h2>Обязательства</h2>
        <div class="list">${commitments}</div>
        <h2>Что помню</h2>
        <div class="list">${memories}</div>
        <h2>Диалоги</h2>
        <div class="list">${conversations}</div>
        <h2>Данные</h2>
        <div class="card">
            <div class="bar" style="margin:0">
                <div class="grow muted">Удаление уносит память, обязательства, эпизоды и диалоги этого человека.</div>
                <button class="btn danger" data-delete-contact="${esc(c.id)}">Удалить контакт</button>
            </div>
        </div>`;
}

pages.conversations = {
    title: 'Диалоги',
    async render(params) {
        const id = params.get('id');
        if (id) return conversationView(id);

        const { conversations } = await api.get('/conversations?limit=50');
        const rows = conversations.length ? conversations.map((c) => `
            <a class="row" href="#/conversations?id=${encodeURIComponent(c.id)}">
                <div class="grow">
                    <div class="title">${esc(c.contact_name || c.title || c.platform)}</div>
                    <div class="sub clip">${esc(c.summary || 'резюме пока не собрано')}</div>
                </div>
                <span class="badge">${esc(c.platform)}</span>
                <div class="when">${ago(c.last_message_at)}</div>
            </a>`).join('') : empty('Диалогов пока нет');

        return `
            <div class="page-head"><h1>Диалоги</h1>
                <p class="lede">Переписка с резюме, эпизодами и тем, что осталось открытым.</p></div>
            <div class="list">${rows}</div>`;
    },
    mount(root) {
        const remove = root.querySelector('[data-delete-conversation]');
        if (!remove) return;
        remove.addEventListener('click', async () => {
            if (!confirm('Удалить диалог со всеми сообщениями и эпизодами?')) return;
            await api.del(`/conversations/${remove.dataset.deleteConversation}`);
            go('conversations', new URLSearchParams());
        });
    },
};

async function conversationView(id) {
    const [conversation, messages] = await Promise.all([
        api.get(`/conversations/${encodeURIComponent(id)}`),
        api.get(`/conversations/${encodeURIComponent(id)}/messages?limit=200`),
    ]);
    if (conversation.error) return empty('Диалог не найден');

    const commitments = conversation.contact_id
        ? (await api.get(`/commitments?status=OPEN&limit=50`)).commitments
            .filter((c) => c.conversation_id === id)
        : [];

    const bubbles = messages.messages.length ? messages.messages.map((m) => {
        const mine = m.sender_type === 'OWNER' || m.sender_type === 'ASSISTANT';
        const kind = m.message_type !== 'TEXT' ? ` · ${m.message_type.toLowerCase()}` : '';
        return `<div class="bubble ${mine ? 'mine' : ''}">
            <div>${esc(m.text || m.transcription || '')}</div>
            <div class="meta">${esc(m.sender_type.toLowerCase())}${kind} · ${esc(clock(m.ts))}</div>
        </div>`;
    }).join('') : empty('Сообщений нет');

    const episodes = (conversation.episodes || []).length
        ? conversation.episodes.map((e) => `
            <div class="row"><div class="grow">
                <div class="title">${esc(e.title || 'Эпизод')}</div>
                <div class="sub">${esc(e.summary || '')}</div>
            </div></div>`).join('')
        : empty('Эпизодов нет');

    const open = commitments.length ? commitments.map((c) => `
        <div class="row"><div class="grow">
            <div class="title">${c.direction === 'I_OWE' ? '→' : '←'} ${esc(c.description)}</div>
            <div class="sub">${c.due_at ? 'до ' + esc(stamp(c.due_at)) : 'без срока'}</div>
        </div></div>`).join('') : empty('Открытых обязательств нет');

    return `
        <div class="page-head">
            <a class="muted" href="#/conversations">← Диалоги</a>
            <h1 style="margin-top:8px">${esc(conversation.title || conversation.platform)}</h1>
            <p class="lede">${esc(conversation.platform)} · ${messages.messages.length} ${plural(messages.messages.length, 'сообщение', 'сообщения', 'сообщений')}</p>
        </div>
        <div class="split">
            <div>
                <h2 style="margin-top:0">Переписка</h2>
                <div class="timeline">${bubbles}</div>
            </div>
            <div>
                <h2 style="margin-top:0">Резюме</h2>
                <div class="card">${esc(conversation.summary || 'Резюме появится после нескольких сообщений.')}</div>
                <h2>Эпизоды</h2>
                <div class="list">${episodes}</div>
                <h2>Обязательства</h2>
                <div class="list">${open}</div>
                <h2>Данные</h2>
                <button class="btn danger" data-delete-conversation="${esc(id)}">Удалить диалог</button>
            </div>
        </div>`;
}

/* Встречу удобнее видеть строкой, одинаковой везде: и на «Сегодня», и здесь. */
function eventRow(event) {
    const start = new Date(event.start * 1000);
    const end = event.end ? new Date(event.end * 1000) : null;
    const clock = (value) => value.toLocaleTimeString('ru-RU',
        { hour: '2-digit', minute: '2-digit' });
    const when = event.all_day ? 'весь день'
        : clock(start) + (end ? '–' + clock(end) : '');
    const day = start.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
    const sub = [event.location, event.calendar].filter(Boolean).join(' · ');

    return `<div class="row">
        <div class="when" style="min-width:96px;text-align:left">
            <div>${esc(day)}</div><div class="faint">${esc(when)}</div></div>
        <div class="grow">
            <div class="title">${esc(event.summary || 'Без названия')}</div>
            ${sub ? `<div class="sub clip">${esc(sub)}</div>` : ''}
        </div>
    </div>`;
}

pages.calendar = {
    title: 'Расписание',
    async render() {
        const data = await api.get('/calendar?days=30');
        if (!data.enabled) {
            return `<div class="page-head"><h1>Расписание</h1></div>
                <div class="card muted">Календарь не подключён. Добавьте
                <b>CALDAV_ACCOUNTS</b> с логином и паролем приложения в окружение
                ядра — встречи появятся здесь и в ответах ассистента.</div>`;
        }

        // Дни, а не сплошной список: «что у меня в четверг» — обычный вопрос.
        const days = new Map();
        data.events.forEach((event) => {
            const key = new Date(event.start * 1000).toLocaleDateString('ru-RU',
                { weekday: 'long', day: 'numeric', month: 'long' });
            if (!days.has(key)) days.set(key, []);
            days.get(key).push(event);
        });

        const schedule = days.size ? [...days].map(([day, events]) => `
            <h3 style="margin-top:22px">${esc(day)}</h3>
            <div class="list" style="margin-top:8px">${events.map(eventRow).join('')}</div>`
        ).join('') : empty('Впереди ничего не запланировано');

        const last = data.last || {};
        const trouble = (last.errors || []).length
            ? `<div class="card bad" style="margin-bottom:16px">Календарь отвечает с
               ошибкой: ${esc(last.errors.join('; '))}. Показано последнее, что
               удалось загрузить.</div>` : '';

        return `
            <div class="page-head"><h1>Расписание</h1>
                <p class="lede">Ближайшие ${data.horizon_days} дней ·
                    ${esc(data.accounts.map((a) => a.address).join(', '))}</p></div>
            ${trouble}
            <div class="card" style="margin-bottom:18px">
                <h3 style="margin:0 0 12px">Записать встречу</h3>
                <div class="form-grid">
                    <input id="event-summary" type="text" placeholder="Название">
                    <input id="event-start" type="datetime-local">
                    <input id="event-minutes" type="number" value="60" min="5" step="5"
                           title="Длительность в минутах">
                    <input id="event-place" type="text" placeholder="Место">
                    <button class="btn primary" id="event-add">Записать</button>
                </div>
                <div class="muted" id="event-note" style="margin-top:10px"></div>
            </div>
            ${schedule}`;
    },
    mount(root) {
        const note = root.querySelector('#event-note');
        root.querySelector('#event-add')?.addEventListener('click', async (e) => {
            const summary = root.querySelector('#event-summary').value.trim();
            const start = root.querySelector('#event-start').value;
            if (!summary || !start) {
                note.textContent = 'Нужны название и время.';
                return;
            }
            e.target.disabled = true;
            note.textContent = 'Записываю…';
            const result = await api.post('/calendar/event', {
                summary, start,
                minutes: Number(root.querySelector('#event-minutes').value) || 60,
                location: root.querySelector('#event-place').value.trim(),
            });
            if (result.status === 'SUCCESS') render();
            else {
                e.target.disabled = false;
                note.textContent = plainError(result.error, 'Не получилось записать.');
            }
        });
    },
};

pages.news = {
    title: 'Новости',
    async render(params) {
        const topic = params.get('topic') || '';
        const data = await api.legacy('/news?limit=24' + (topic ? `&topic=${encodeURIComponent(topic)}` : ''));

        const chips = ['', ...(data.topics || [])].map((value) => `
            <button class="chip ${value === topic ? 'on' : ''}" data-topic="${esc(value)}">
                ${esc(value || 'Все')}</button>`).join('');

        const items = (data.items || []).length ? data.items.map((item) => `
            <a class="row" href="${esc(item.link)}" target="_blank" rel="noreferrer">
                <div class="grow">
                    <div class="title">${esc(item.title)}</div>
                    <div class="sub">${esc(item.summary || '')}</div>
                    <div class="sub faint">${esc((item.sources || []).join(' · '))}</div>
                </div>
                <span class="badge">${esc(item.topic_title || item.topic || '')}</span>
                <div class="when">${esc(item.when || '')}</div>
            </a>`).join('') : empty('Новостей нет');

        return `
            <div class="page-head"><h1>Новости</h1>
                <p class="lede">Сюжеты, а не лента: одинаковые новости сведены по источникам.</p></div>
            <div class="chips" style="margin-bottom:16px">${chips}</div>
            <div class="list">${items}</div>`;
    },
    mount(root, params) {
        root.querySelectorAll('[data-topic]').forEach((chip) => {
            chip.addEventListener('click', () => {
                const next = new URLSearchParams(params);
                if (chip.dataset.topic) next.set('topic', chip.dataset.topic);
                else next.delete('topic');
                go('news', next);
            });
        });
    },
};

pages.activity = {
    title: 'Активность',
    async render(params) {
        const correlation = params.get('corr') || '';
        const path = '/activity?limit=120' + (correlation ? `&correlation_id=${encodeURIComponent(correlation)}` : '');
        const { activity } = await api.get(path);

        const rows = activity.length ? activity.map((item) => `
            <div class="row">
                <div class="stamp">${esc(clock(item.ts))}</div>
                <div class="grow">
                    <div class="event">${esc(item.event)}</div>
                    <div class="sub clip">${esc(item.actor || '')}${item.entity_id ? ' · ' + esc(item.entity_id) : ''}</div>
                </div>
                ${item.correlation_id ? `<a class="corr" href="#/activity?corr=${encodeURIComponent(item.correlation_id)}">${esc(item.correlation_id)}</a>` : ''}
            </div>`).join('') : empty('Журнал пуст');

        return `
            <div class="page-head"><h1>Активность</h1>
                <p class="lede">Каждое действие ассистента. Нажми на цепочку, чтобы увидеть её целиком.</p></div>
            ${correlation ? `<div class="bar"><span class="badge accent">цепочка ${esc(correlation)}</span>
                <a class="btn ghost" href="#/activity">Показать всё</a></div>` : ''}
            <div class="list trace">${rows}</div>`;
    },
};

const ACTION_TONE = {
    SUCCESS: 'ok', FAILED: 'bad', CANCELLED: 'warn', EXPIRED: 'warn',
    WAITING_APPROVAL: 'accent', RUNNING: 'accent',
};

pages.actions = {
    title: 'Действия',
    async render() {
        const { actions } = await api.get('/actions?limit=60');
        const rows = actions.length ? actions.map((a) => {
            const waiting = a.status === 'WAITING_APPROVAL';
            return `<div class="row">
                <div class="grow">
                    <div class="title">${esc(a.type)}</div>
                    <div class="sub clip">${esc(JSON.stringify(a.parameters))}</div>
                    <div class="sub faint">${esc(a.requested_by || '')} · риск ${esc((a.risk_level || '').toLowerCase())}${a.error ? ' · ' + esc(a.error) : ''}</div>
                </div>
                <span class="badge ${ACTION_TONE[a.status] || ''}">${esc(a.status.toLowerCase())}</span>
                <div class="when">${ago(a.created_at)}</div>
                ${waiting ? `<div class="actions">
                    <button class="btn primary" data-approve="${esc(a.id)}">Подтвердить</button>
                    <button class="btn ghost" data-cancel="${esc(a.id)}">Отменить</button>
                </div>` : ''}
            </div>`;
        }).join('') : empty('Действий пока не было');

        return `
            <div class="page-head"><h1>Действия</h1>
                <p class="lede">Всё, что ассистент делает наружу, проходит здесь.</p></div>
            <div class="list">${rows}</div>`;
    },
    mount(root) {
        root.querySelectorAll('[data-approve]').forEach((button) => {
            button.addEventListener('click', async () => {
                await api.post(`/actions/${button.dataset.approve}/approve`, { actor: 'web' });
                render();
            });
        });
        root.querySelectorAll('[data-cancel]').forEach((button) => {
            button.addEventListener('click', async () => {
                await api.post(`/actions/${button.dataset.cancel}/cancel`, { actor: 'web' });
                render();
            });
        });
    },
};

pages.integrations = {
    title: 'Интеграции',
    async render() {
        const { integrations } = await api.get('/integrations?refresh=true');
        const rows = integrations.map((i) => {
            const tone = i.status === 'CONNECTED' ? 'ok' : i.status === 'ERROR' ? 'bad' : 'warn';
            return `<div class="row">
                <span class="badge ${tone}"><span class="dot"></span>${esc(i.status.toLowerCase())}</span>
                <div class="grow">
                    <div class="title">${esc(i.name)}</div>
                    <div class="sub clip">${esc(i.detail || '')}</div>
                </div>
                <span class="badge">${esc(i.type)}</span>
                ${i.required ? '<span class="badge">обязательна</span>' : ''}
                <div class="when">${ago(i.checked_at)}</div>
            </div>`;
        }).join('');

        return `
            <div class="page-head"><h1>Интеграции</h1>
                <p class="lede">Состояние проверяется в момент открытия страницы.</p></div>
            <div class="list">${rows}</div>`;
    },
};

pages.notifications = {
    title: 'Уведомления',
    async render() {
        const [history, digest] = await Promise.all([
            api.get('/notifications?limit=50'),
            api.get('/notifications/digest?limit=30'),
        ]);

        const row = (n) => `
            <div class="row">
                <div class="grow">
                    <div class="title">${esc(n.title)}</div>
                    <div class="sub clip">${esc(n.body || '')}</div>
                </div>
                <span class="badge">${esc(n.severity)}</span>
                <span class="badge">${esc((n.status || '').toLowerCase())}</span>
                <div class="when">${ago(n.created_at)}</div>
            </div>`;

        const shown = history.notifications.length
            ? history.notifications.map(row).join('') : empty('Уведомлений не было');
        const later = digest.items.length
            ? digest.items.map(row).join('') : empty('В дайджесте пусто');

        return `
            <div class="page-head"><h1>Уведомления</h1>
                <p class="lede">Политика решает: сказать сразу, отложить в дайджест или промолчать.</p></div>
            <h2>История</h2>
            <div class="list">${shown}</div>
            <h2>Отложено в дайджест</h2>
            <div class="list">${later}</div>`;
    },
};

pages.settings = {
    title: 'Настройки',
    async render() {
        const [health, permissions, mail] = await Promise.all([
            api.get('/health'), api.get('/permissions'), api.get('/mail'),
        ]);
        state.security = health.security;

        const decisions = ['ALLOW', 'REQUIRE_APPROVAL', 'DENY'];
        const rows = Object.entries(permissions.risk_levels).map(([type, risk]) => {
            const override = permissions.overrides[type];
            const fallback = permissions.defaults[risk];
            const options = decisions.map((value) => `
                <option value="${value}" ${override === value ? 'selected' : ''}>${value}</option>`).join('');
            return `<div class="row">
                <div class="grow">
                    <div class="title">${esc(type)}</div>
                    <div class="sub">риск ${esc(risk.toLowerCase())} · по умолчанию ${esc(fallback.toLowerCase())}</div>
                </div>
                <select data-permission="${esc(type)}" style="width:190px">
                    <option value="">по умолчанию</option>${options}
                </select>
            </div>`;
        }).join('');

        return `
            <div class="page-head"><h1>Настройки</h1>
                <p class="lede">Режим ответов, права на действия и доступ к панели.</p></div>
            ${securityNotice()}

            <h2>Режим ответов</h2>
            <div class="card">
                <h3>${esc(health.response_mode)}</h3>
                <div class="muted">SUGGEST_ONLY — JARVIS только предлагает варианты,
                    отправляет всегда владелец. Автоотправка не включена.</div>
            </div>

            <h2>Почта</h2>
            ${mailSection(mail)}

            <h2>Права на действия</h2>
            <div class="list">${rows}</div>

            <h2>Доступ к панели</h2>
            <div class="card">
                <div class="muted" style="margin-bottom:12px">
                    ${state.security?.auth === 'token'
                ? 'Доступ закрыт токеном. С самой машины (127.0.0.1) токен не нужен — так ходят бот и tg-user.'
                : 'Токен не задан: любой в сети может открыть панель. Задайте ASSISTANT_WEB_TOKEN в окружении сервиса.'}
                </div>
                <div class="bar" style="margin:0">
                    <input class="grow" type="password" id="token" placeholder="Токен доступа"
                           value="${esc(token.get())}">
                    <button class="btn" id="save-token">Сохранить</button>
                    <button class="btn ghost" id="forget-token">Забыть</button>
                </div>
            </div>`;
    },
    mount(root) {
        root.querySelectorAll('[data-permission]').forEach((select) => {
            select.addEventListener('change', async () => {
                await api.post('/permissions/override', {
                    action_type: select.dataset.permission,
                    decision: select.value || null,
                });
                render();
            });
        });
        root.querySelectorAll('[data-unmute]').forEach((button) => {
            button.addEventListener('click', async () => {
                await api.post('/mail/sender',
                    { address: button.dataset.unmute, robot: false });
                render();
            });
        });
        root.querySelector('#check-mail')?.addEventListener('click', async (event) => {
            event.target.disabled = true;
            event.target.textContent = 'Проверяю…';
            await api.post('/mail/check');
            render();
        });
        root.querySelector('#save-token').addEventListener('click', () => {
            token.set(root.querySelector('#token').value.trim());
            render();
        });
        root.querySelector('#forget-token').addEventListener('click', () => {
            token.clear();
            render();
        });
    },
};

function mailSection(mail) {
    if (!mail.enabled) {
        return `<div class="card muted">Ящики не подключены. Добавьте
            <b>MAIL_ACCOUNTS</b> и логин с паролем приложения в окружение ядра —
            письма попадут в те же «Входящие», что и сообщения.</div>`;
    }
    const last = mail.last || {};
    const boxes = mail.accounts.map((a) => `
        <div class="row"><div class="grow">
            <div class="title">${esc(a.address)}</div>
            <div class="sub">${esc(a.name)}</div>
        </div></div>`).join('');

    const report = last.at
        ? `Последняя проверка ${ago(last.at)}: новых ${last.new || 0},
           отсеяно ${last.skipped || 0}, старых ${last.stale || 0}${(last.errors || []).length
            ? ', ошибки: ' + esc(last.errors.join('; ')) : ''}`
        : `Проверка каждые ${Math.round(mail.poll_seconds / 60)} мин, ещё не было.`;

    // Отсеянное не должно пропадать молча: если сюда попал человек, владелец
    // это увидит и вернёт его одной кнопкой.
    const skipped = (last.skipped_senders || []).length
        ? `<h3 style="margin-top:22px">Отсеяно как роботы</h3>
           <div class="list" style="margin-top:8px">${last.skipped_senders.map((s) => `
               <div class="row"><div class="grow">
                   <div class="title">${esc(s.address)}</div>
                   <div class="sub">${s.count} ${plural(s.count, 'письмо', 'письма', 'писем')}</div>
               </div>
               <div class="actions">
                   <button class="btn ghost" data-unmute="${esc(s.address)}">Это человек</button>
               </div></div>`).join('')}</div>`
        : '';

    const muted = (mail.muted || []).length
        ? `<h3 style="margin-top:22px">Заглушены вручную</h3>
           <div class="chips" style="margin-top:8px">${mail.muted.map((address) => `
               <button class="chip" data-unmute="${esc(address)}">${esc(address)} ✕</button>`).join('')}</div>`
        : '';

    return `<div class="list">${boxes}</div>
        <div class="bar" style="margin-top:12px">
            <div class="grow muted">${report}</div>
            <button class="btn" id="check-mail">Проверить сейчас</button>
        </div>
        ${skipped}${muted}`;
}

function securityNotice() {
    if (state.security?.auth !== 'open') return '';
    return `<div class="notice">${esc(state.security.warning)}</div>`;
}

/* --- маршрутизация ------------------------------------------------------ */
function route() {
    const raw = location.hash.replace(/^#\/?/, '');
    const [path, query] = raw.split('?');
    return { path: path || '', params: new URLSearchParams(query || '') };
}

function go(path, params) {
    const query = params && params.toString() ? '?' + params.toString() : '';
    location.hash = `#/${path}${query}`;
}

function gate(message) {
    document.getElementById('root').innerHTML = `
        <div class="gate">
            <div class="card">
                <h1 style="font-size:20px">JARVIS</h1>
                <p class="lede" style="margin-bottom:18px">${esc(message)}</p>
                <input type="password" id="gate-token" placeholder="Токен доступа" autofocus>
                <button class="btn primary" id="gate-go" style="width:100%;margin-top:12px">Войти</button>
            </div>
        </div>`;
    const submit = () => {
        const value = document.getElementById('gate-token').value.trim();
        if (!value) return;
        token.set(value);
        render();
    };
    document.getElementById('gate-go').addEventListener('click', submit);
    document.getElementById('gate-token').addEventListener('keydown', (event) => {
        if (event.key === 'Enter') submit();
    });
}

let rendering = false;

async function render() {
    if (rendering) return;
    rendering = true;
    const { path, params } = route();
    const page = pages[path] || pages[''];
    const root = document.getElementById('root');

    try {
        if (state.security === null) {
            state.security = (await api.get('/health')).security;
        }
        if (path !== '') {
            // Счётчики в навигации живут на главной сводке.
            state.overview = state.overview || await api.get('/overview');
        }

        const body = await page.render(params);
        root.innerHTML = `<div class="shell">${sidebar(path)}<main class="main">${body}</main></div>`;
        page.mount?.(root, params);
        document.title = `${page.title} · JARVIS`;
        bindChrome(root);
    } catch (error) {
        if (error instanceof Unauthorized) {
            rendering = false;
            gate(token.get() ? 'Токен не подошёл.' : 'Панель закрыта токеном.');
            return;
        }
        root.innerHTML = `<div class="shell">${sidebar(path)}<main class="main">
            <div class="page-head"><h1>Не открылось</h1>
                <p class="lede">${esc(error.message)}</p></div>
            <button class="btn" onclick="location.reload()">Обновить</button>
        </main></div>`;
        bindChrome(root);
    } finally {
        rendering = false;
    }
}

function bindChrome(root) {
    root.querySelector('[data-theme-toggle]')?.addEventListener('click', () => {
        const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
        document.documentElement.dataset.theme = next;
        localStorage.setItem(THEME_KEY, next);
    });
}

document.documentElement.dataset.theme = localStorage.getItem(THEME_KEY) || 'dark';
window.addEventListener('hashchange', () => {
    state.overview = null;      // счётчики пересчитываются при переходе
    render();
});
render();
