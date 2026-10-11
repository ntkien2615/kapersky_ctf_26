const samples = document.querySelector("#samples")
const target = document.querySelector("#target")
const hint = document.querySelector("#hint")
const form = document.querySelector("#guess-form")
const input = document.querySelector("#guess")
const submit = document.querySelector("#submit")
const result = document.querySelector("#result")
const dealButton = document.querySelector("#new-round")
const handCards = [...document.querySelectorAll(".hand-card")]

let game = null
let selected = null
let timerId = null

function setHint(text, type = "") {
  hint.textContent = text
  hint.className = type
}

function stopTimer() {
  clearInterval(timerId)
  timerId = null
}

function lockBet() {
  input.disabled = true
  submit.disabled = true
  handCards.forEach(card => card.disabled = true)
}

function checkDeadline() {
  if (!game) return
  const left = Math.max(0, Math.ceil((game.deadline - Date.now()) / 1000))
  if (!left) {
    stopTimer()
    game = null
    selected = null
    lockBet()
    setHint("The round is over. Deal again.", "bad")
  }
}

function makeCard(value, index, suit) {
  const card = document.createElement("article")
  const number = String(index + 1).padStart(2, "0")
  const suitClass = { "♠": "spade", "♥": "heart", "♦": "diamond", "♣": "club" }[suit]
  card.className = `signal-card ${suitClass}`
  card.innerHTML = `
    <span class="card-corner top"><b>${number}</b>${suit}</span>
    <span class="card-value"><code></code></span>
    <span class="card-corner bottom"><b>${number}</b>${suit}</span>`
  card.querySelector("code").textContent = value
  return card
}

function shuffledSuits(count) {
  const suits = Array.from({ length: count }, (_, index) => ["♠", "♥", "♦", "♣"][index % 4])
  for (let index = suits.length - 1; index > 0; index--) {
    const other = Math.floor(Math.random() * (index + 1))
    const suit = suits[index]
    suits[index] = suits[other]
    suits[other] = suit
  }
  return suits
}

function renderGame(data) {
  game = { ...data, deadline: Date.now() + data.ttl * 1000 }
  selected = null
  result.hidden = true
  result.textContent = ""
  input.value = ""
  input.disabled = true
  submit.disabled = true
  target.textContent = data.target
  const suits = shuffledSuits(data.samples.length)
  samples.replaceChildren(...data.samples.map((value, index) => makeCard(value, index, suits[index])))
  handCards.forEach(card => {
    card.classList.remove("selected")
    card.setAttribute("aria-pressed", "false")
    card.disabled = false
  })
  setHint("Choose one face-down card.")
  stopTimer()
  checkDeadline()
  timerId = setInterval(checkDeadline, 1000)
}

async function deal() {
  stopTimer()
  game = null
  selected = null
  lockBet()
  dealButton.disabled = true
  result.hidden = true
  result.textContent = ""
  samples.innerHTML = '<div class="loading">dealer is shuffling…</div>'
  try {
    const response = await fetch("/api/deal", { cache: "no-store" })
    if (!response.ok) throw new Error()
    renderGame(await response.json())
  } catch {
    samples.innerHTML = '<div class="loading">table is unavailable</div>'
    setHint("Could not get a deal.", "bad")
  } finally {
    dealButton.disabled = false
  }
}

handCards.forEach(card => {
  card.addEventListener("click", () => {
    if (!game || card.disabled) return
    selected = Number(card.dataset.slot)
    handCards.forEach(other => {
      const active = other === card
      other.classList.toggle("selected", active)
      other.setAttribute("aria-pressed", String(active))
    })
    input.disabled = false
    submit.disabled = false
    input.focus()
    setHint(`Selected the ${selected === 0 ? "left" : "right"} card. Enter its x-coordinate.`)
  })
})

form.addEventListener("submit", async event => {
  event.preventDefault()
  if (!game || selected === null) return
  const value = input.value.trim()
  if (!/^\d{1,80}$/.test(value)) {
    setHint("Enter a decimal x-coordinate without spaces or a sign.", "bad")
    return
  }

  lockBet()
  try {
    const response = await fetch("/api/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: game.id, slot: selected, value })
    })
    const data = await response.json()
    result.hidden = false
    result.className = `result ${data.ok ? "win" : "lose"}`
    result.textContent = data.message
    stopTimer()
    game = null
    selected = null
    setHint(data.ok ? "Bet accepted." : "Round closed.", data.ok ? "good" : "bad")
  } catch {
    game = null
    selected = null
    setHint("Failed to submit the bet.", "bad")
  }
})

dealButton.addEventListener("click", deal)
deal()
