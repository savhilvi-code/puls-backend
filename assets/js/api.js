import { API_BASE_URL } from "./config.js";

export async function loadHistoryFromApi(userId) {
  const res = await fetch(`${API_BASE_URL}/api/history?userId=${encodeURIComponent(userId)}`);
  if (!res.ok) throw new Error("history api error");
  const data = await res.json();
  return Array.isArray(data.items) ? data.items : [];
}

export async function saveHistoryToApi({ userId, question, answer, type, vehicle }) {
  const res = await fetch(`${API_BASE_URL}/api/history`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ userId, question, answer, type, vehicle })
  });

  if (!res.ok) throw new Error("save history api error");
  return res.json();
}

export async function sendChatMessage({ prompt, userId, vehicle }) {
  const res = await fetch(`${API_BASE_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, userId, vehicle })
  });

  if (!res.ok) throw new Error("api chat вернул ошибку");
  return res.json();
}
