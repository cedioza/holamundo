const expressionEl = document.querySelector('#expression');
const resultEl = document.querySelector('#result');
const historyEl = document.querySelector('#history');
const emptyHistoryEl = document.querySelector('#empty-history');
const clearHistoryButton = document.querySelector('#clear-history');
const keys = document.querySelectorAll('.key');

let expression = '';
let result = '0';
let justCalculated = false;
let history = [];

const operatorPattern = /[+−×÷]/;

function formatNumber(value) {
  if (!Number.isFinite(value)) return 'Error';
  const rounded = Number.parseFloat(value.toPrecision(12));
  return new Intl.NumberFormat('es-ES', { maximumFractionDigits: 10 }).format(rounded);
}

function render() {
  expressionEl.textContent = expression || '0';
  resultEl.textContent = result;
}

function currentNumberStart() {
  const match = expression.match(/[+−×÷][^+−×÷]*$/);
  return match ? expression.length - match[0].length + 1 : 0;
}

function appendValue(value) {
  if (result === 'Error') reset();
  const wasCalculated = justCalculated;
  if (wasCalculated && !operatorPattern.test(value)) expression = '';
  justCalculated = false;

  if (operatorPattern.test(value)) {
    if (!expression) expression = result !== '0' ? result : '0';
    if (operatorPattern.test(expression.at(-1))) expression = expression.slice(0, -1) + value;
    else expression += value;
  } else if (value === '.') {
    const start = currentNumberStart();
    const current = expression.slice(start);
    if (!current.includes('.')) expression += current ? '.' : '0.';
  } else {
    const start = currentNumberStart();
    const current = expression.slice(start);
    if (expression === '0' || (wasCalculated && !operatorPattern.test(value))) expression = value;
    else if (current === '0') expression = expression.slice(0, start) + value;
    else expression += value;
  }

  updatePreview();
}

function updatePreview() {
  if (!expression || operatorPattern.test(expression.at(-1))) {
    result = expression || '0';
    render();
    return;
  }

  try {
    result = formatNumber(evaluate(expression));
  } catch {
    result = '…';
  }
  render();
}

function reset() {
  expression = '';
  result = '0';
  justCalculated = false;
  render();
}

function backspace() {
  if (justCalculated) return reset();
  expression = expression.slice(0, -1);
  updatePreview();
}

function toggleSign() {
  if (!expression) expression = '−';
  else {
    const start = currentNumberStart();
    const current = expression.slice(start);
    if (current.startsWith('−')) expression = expression.slice(0, start) + current.slice(1);
    else expression = expression.slice(0, start) + '−' + current;
  }
  updatePreview();
}

function applyPercent() {
  const start = currentNumberStart();
  const current = expression.slice(start);
  const number = Number(current.replace('−', '-'));
  if (current && Number.isFinite(number)) {
    expression = expression.slice(0, start) + String(number / 100);
    updatePreview();
  }
}

function calculate() {
  if (!expression || operatorPattern.test(expression.at(-1))) return;
  try {
    const value = evaluate(expression);
    result = formatNumber(value);
    addHistory(expression, result);
    expression = String(value);
    justCalculated = true;
    render();
  } catch {
    result = 'Error';
    render();
  }
}

function tokenize(input) {
  const normalized = input.replaceAll('−', '-').replaceAll('×', '*').replaceAll('÷', '/');
  const tokens = normalized.match(/\d*\.?\d+|[+*/-]/g);
  if (!tokens || tokens.join('') !== normalized) throw new Error('Expresión inválida');
  return tokens;
}

function evaluate(input) {
  const tokens = tokenize(input);
  let index = 0;

  function parseExpression() {
    let value = parseTerm();
    while (tokens[index] === '+' || tokens[index] === '-') {
      const operator = tokens[index++];
      const right = parseTerm();
      value = operator === '+' ? value + right : value - right;
    }
    return value;
  }

  function parseTerm() {
    let value = parseNumber();
    while (tokens[index] === '*' || tokens[index] === '/') {
      const operator = tokens[index++];
      const right = parseNumber();
      if (operator === '/' && right === 0) throw new Error('No se puede dividir por cero');
      value = operator === '*' ? value * right : value / right;
    }
    return value;
  }

  function parseNumber() {
    const token = tokens[index++];
    if (token === '-') {
      const next = tokens[index++];
      if (!next || !/^\d*\.?\d+$/.test(next)) throw new Error('Número incompleto');
      return -Number(next);
    }
    if (!token || ['+', '*', '/'].includes(token)) throw new Error('Número incompleto');
    return Number(token);
  }

  const value = parseExpression();
  if (index !== tokens.length || !Number.isFinite(value)) throw new Error('Expresión inválida');
  return value;
}

function addHistory(input, output) {
  history.unshift({ input, output, time: new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' }) });
  history = history.slice(0, 8);
  renderHistory();
}

function renderHistory() {
  historyEl.replaceChildren();
  if (!history.length) {
    historyEl.append(emptyHistoryEl);
    return;
  }
  history.forEach(({ input, output, time }) => {
    const entry = document.createElement('div');
    const expressionText = document.createElement('p');
    const resultText = document.createElement('strong');
    const timeText = document.createElement('p');

    entry.className = 'history-entry';
    expressionText.className = 'history-expression';
    resultText.className = 'history-result';
    timeText.className = 'history-time';
    expressionText.textContent = input;
    resultText.textContent = output;
    timeText.textContent = time;

    entry.append(expressionText, resultText, timeText);
    historyEl.append(entry);
  });
}

function handleAction(action) {
  if (action === 'clear') reset();
  if (action === 'backspace') backspace();
  if (action === 'percent') applyPercent();
  if (action === 'sign') toggleSign();
  if (action === 'equals') calculate();
}

keys.forEach((key) => {
  key.addEventListener('click', () => {
    if (key.dataset.action) handleAction(key.dataset.action);
    else appendValue(key.dataset.value);
  });
});

clearHistoryButton.addEventListener('click', () => {
  history = [];
  renderHistory();
});

document.addEventListener('keydown', (event) => {
  if (/\d/.test(event.key)) appendValue(event.key);
  else if (event.key === '.') appendValue('.');
  else if (event.key === '+') appendValue('+');
  else if (event.key === '-') appendValue('−');
  else if (event.key === '*') appendValue('×');
  else if (event.key === '/') { event.preventDefault(); appendValue('÷'); }
  else if (event.key === 'Enter' || event.key === '=') calculate();
  else if (event.key === 'Backspace') backspace();
  else if (event.key === 'Escape') reset();
  else if (event.key === '%') applyPercent();
});

render();
