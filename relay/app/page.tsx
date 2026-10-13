import { redirect } from "next/navigation";
import { chatGPTSignInPath } from "./chatgpt-auth";
import { ownerId, agentState } from "../lib/phone-relay";
export const dynamic = "force-dynamic";
type HomeProps = { searchParams: Promise<{ lang?: string | string[] }> };

const copy = {
  en: {
    title: "Codaki Mini Codex 0.2.5 — phone",
    description: "A personal agent for phone control and compressed task memory.",
    eyebrow: "Personal tool",
    heading: "Codaki Mini Codex 0.2.5",
    intro: "Control your phone from ChatGPT.",
    phone: "Phone",
    online: "Agent connected",
    pending: "Waiting for the agent to connect",
    execution: "Commands run on the phone itself. After verifying the connection, you can switch off your computer.",
    memory: "Task memory",
    storage: "Short notes and compressed archives — up to 5 GiB in total. Storage fills gradually; the oldest records are removed when the limit is reached.",
    preferences: "Memory stores preferences and verified ways to complete tasks.",
    connection: "Connect to ChatGPT",
    plugin: 'Add your personal “Codaki Mini Codex — phone” plugin and select it in the conversation. Start with “Check my phone’s status.”',
    open: "Open ChatGPT plugins",
    footnote: "Access is tied to your account. To stop the agent, disable the Codaki Mini Codex module in Magisk.",
  },
  ru: {
    title: "Codaki Mini Codex 0.2.5 — телефон",
    description: "Личный агент для управления телефоном и сжатой памяти задач.",
    eyebrow: "Личный инструмент",
    heading: "Codaki Mini Codex 0.2.5",
    intro: "Управление твоим телефоном из ChatGPT.",
    phone: "Телефон",
    online: "Агент подключён",
    pending: "Ожидаем подключение агента",
    execution: "Команды выполняются на самом телефоне. После проверки подключения компьютер можно отключить.",
    memory: "Память задач",
    storage: "Краткие заметки и сжатые архивы — вместе до 5 GiB. Место заполняется постепенно; самые старые записи удаляются при достижении лимита.",
    preferences: "В памяти сохраняются предпочтения и проверенные способы выполнения задач.",
    connection: "Подключение к ChatGPT",
    plugin: "Добавь личный плагин «Codaki Mini Codex — телефон» и выбери его в разговоре. Начни с команды «Проверь состояние моего телефона».",
    open: "Открыть плагины ChatGPT",
    footnote: "Доступ закреплён за твоим аккаунтом. Агент можно остановить, отключив модуль «Codaki Mini Codex» в Magisk.",
  },
};

async function language(searchParams: HomeProps["searchParams"]) {
  return (await searchParams).lang === "ru" ? "ru" : "en";
}

export async function generateMetadata({ searchParams }: HomeProps) {
  const text = copy[await language(searchParams)];
  return { title: text.title, description: text.description };
}

export default async function Home({ searchParams }: HomeProps) {
  const lang = await language(searchParams);
  const text = copy[lang];
  if (!await ownerId()) redirect(chatGPTSignInPath(lang === "ru" ? "/?lang=ru" : "/"));
  const state = await agentState();
  return <main className="phone-panel" lang={lang}>
    <nav aria-label={lang === "ru" ? "Язык" : "Language"}>
      <a href="/?lang=en" lang="en" aria-current={lang === "en" ? "page" : undefined}>English</a>
      {" · "}
      <a href="/?lang=ru" lang="ru" aria-current={lang === "ru" ? "page" : undefined}>Русский</a>
    </nav>
    <p className="eyebrow">{text.eyebrow}</p>
    <h1>{text.heading}</h1>
    <p className="intro">{text.intro}</p>
    <section className="phone-card" aria-labelledby="connection">
      <h2 id="connection">{text.phone}</h2>
      <p className={state.online ? "online" : "pending"}>{state.online ? text.online : text.pending}</p>
      <p>{text.execution}</p>
    </section>
    <section className="phone-card" aria-labelledby="memory">
      <h2 id="memory">{text.memory}</h2>
      <p>{text.storage}</p>
      <p>{text.preferences}</p>
    </section>
    <section className="phone-card" aria-labelledby="chatgpt">
      <h2 id="chatgpt">{text.connection}</h2>
      <p>{text.plugin}</p>
      <a className="phone-button" href="https://chatgpt.com/plugins" target="_top">{text.open}</a>
    </section>
    <p className="footnote">{text.footnote}</p>
  </main>;
}
