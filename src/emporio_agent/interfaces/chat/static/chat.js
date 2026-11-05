const conversation = document.querySelector("#conversation");
const messages = document.querySelector("#messages");
const welcome = document.querySelector("#welcome");
const form = document.querySelector("#composer");
const input = document.querySelector("#message");
const send = document.querySelector("#send");
const clear = document.querySelector("#clear");
const customer = document.querySelector("#customer");
const status = document.querySelector("#status");
let state = { messages: [], customer_id: null, customer_ids: [] };
let busy = false;

function setBusy(value) {
  busy = value;
  for (const element of [input, send, clear, customer, ...document.querySelectorAll("[data-prompt]")]) {
    element.disabled = value;
  }
  form.setAttribute("aria-busy", String(value));
}

function appendMessage(role, content, typing = false) {
  const item = document.createElement("article");
  item.className = `message ${role}${typing ? " typing" : ""}`;
  const label = document.createElement("span");
  label.className = "message-label";
  label.textContent = role === "user" ? "Você" : "Empório da Música";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  // Renderiza somente negrito simples; HTML recebido é sempre tratado como texto.
  content.split(/(\*\*[^*]+\*\*)/g).forEach(part => {
    if (part.startsWith("**") && part.endsWith("**")) {
      const strong = document.createElement("strong");
      strong.textContent = part.slice(2, -2);
      bubble.append(strong);
    } else bubble.append(document.createTextNode(part));
  });
  item.append(label, bubble);
  messages.append(item);
}

function render() {
  messages.replaceChildren();
  welcome.hidden = state.messages.length > 0;
  state.messages.forEach(message => appendMessage(message.role, message.content));
  customer.value = state.customer_id === null ? "" : String(state.customer_id);
  document.querySelector("#session-note").textContent = state.customer_id === null
    ? "Sem acesso a pedidos" : "Identidade simulada · não é autenticação";
  conversation.scrollTop = conversation.scrollHeight;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options, headers: { "Content-Type": "application/json" }, credentials: "same-origin",
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Não foi possível concluir a solicitação.");
  return data;
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text || busy) return;
  setBusy(true);
  status.textContent = "Consultando as informações para você…";
  welcome.hidden = true;
  appendMessage("user", text);
  appendMessage("assistant", "Preparando sua resposta…", true);
  conversation.scrollTop = conversation.scrollHeight;
  try {
    state = await api("/api/messages", { method: "POST", body: JSON.stringify({ message: text }) });
    input.value = "";
    status.textContent = "";
  } catch (error) {
    status.textContent = error.message || "Falha de conexão. Tente novamente.";
  } finally {
    render();
    setBusy(false);
    input.focus();
  }
});

input.addEventListener("keydown", event => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    form.requestSubmit();
  }
});

async function reset(customerId) {
  if (busy) return;
  setBusy(true);
  status.textContent = "Iniciando nova conversa…";
  try {
    state = await api("/api/session", { method: "POST", body: JSON.stringify({ customer_id: customerId }) });
    input.value = "";
    status.textContent = "";
  } catch (error) {
    status.textContent = error.message || "Falha de conexão.";
  } finally {
    render();
    setBusy(false);
    input.focus();
  }
}

clear.addEventListener("click", () => reset(state.customer_id));
customer.addEventListener("change", () => reset(customer.value === "" ? null : Number(customer.value)));
document.querySelectorAll("[data-prompt]").forEach(button => button.addEventListener("click", () => {
  input.value = button.dataset.prompt;
  form.requestSubmit();
}));

async function start() {
  setBusy(true);
  try {
    state = await api("/api/session");
    for (const id of state.customer_ids) {
      const option = document.createElement("option");
      option.value = String(id);
      option.textContent = `Cliente de teste ${id}`;
      customer.append(option);
    }
    render();
    setBusy(false);
    input.focus();
  } catch (error) {
    status.textContent = "Não foi possível iniciar. Recarregue a página para tentar novamente.";
  }
}
start();
