'use strict';
const $ = id => document.getElementById(id);
let token = '', snapshot = null, selected = '', connected = false, polling = false, promptKey = '', renderKey = '', pendingAnswer = false;
let information = null;
const text = (tag, value) => { const element = document.createElement(tag); element.textContent = value ?? ''; return element; };
async function api(path, data, credential = token) {
  const response = await fetch(path, {method: data === undefined ? 'GET' : 'POST', cache: 'no-store',
    headers: {'Authorization': 'Bearer ' + credential, 'Content-Type': 'application/json'},
    body: data === undefined ? undefined : JSON.stringify(data)});
  const result = await response.json(); if (!response.ok) throw new Error(result.error || 'Request failed'); return result;
}
function error(value) { $('error').textContent = value?.message || value || ''; }
function current() { return snapshot?.runs.find(run => run.id === selected); }
function canControl(run) { return !!(connected && run?.active && run.controlling && !run.pending); }
async function refresh() {
  if (!token || polling) return;
  polling = true;
  try {
    snapshot = await api('/api/state'); connected = true; $('connection').textContent = 'Connected';
    if (!selected && snapshot.runs.length) selected = snapshot.runs[0].id;
    render();
  } catch (failure) {
    connected = false; $('connection').textContent = 'Disconnected · reconnect required'; error(failure); render();
  } finally { polling = false; }
}
function render() {
  if (!snapshot) return;
  const run = current(); const controlling = canControl(run);
  const history = $('history'); history.replaceChildren();
  for (const entry of snapshot.runs) {
    const name = entry.script.split(/[\\/]/).pop(); const button = text('button', `${name} · ${entry.id.slice(0, 6)} · ${entry.status}`);
    button.setAttribute('aria-current', String(entry.id === selected));
    button.onclick = () => { selected = entry.id; renderKey = ''; render(); }; history.append(button);
  }
  $('run').disabled = !connected || snapshot.role !== 'operator' || snapshot.runs.filter(r => r.active).length >= snapshot.capabilities.maxInstances || snapshot.runs.some(r => r.active && (r.pending || !['PAUSED', 'INTERRUPTED'].includes(r.status)));
  $('title').textContent = run ? run.script.split(/[\\/]/).pop() + ' · ' + run.id.slice(0, 6) : 'Choose a procedure';
  $('step').textContent = run?.step || '';
  $('state').textContent = run?.status || 'Ready'; $('state').style.background = snapshot.colors.procedure[run?.status] || '#fff';
  const owns = connected && run?.active && run.controlling;
  $('role').textContent = run && !run.active ? 'Record' : owns ? 'CTRL' : 'MON'; $('role').style.color = owns ? '#008000' : '#0000ff';
  $('role').title = run?.controller ? 'Controller: ' + run.controller : 'No controller';
  $('pending').textContent = run?.pending ? 'Awaiting native acknowledgement: ' + run.pending : '';
  $('claim').disabled = !connected || !run?.active || !!run.controller || snapshot.role !== 'operator';
  $('release').disabled = !controlling || !['PAUSED', 'INTERRUPTED', 'PROMPT'].includes(run.status);
  for (const button of document.querySelectorAll('[data-command]')) {
    const command = button.dataset.command;
    button.disabled = !controlling || (['continue', 'next', 'stepIn'].includes(command) && !['PAUSED', 'INTERRUPTED'].includes(run.status)) || (command === 'pause' && ['PAUSED', 'INTERRUPTED'].includes(run.status));
  }
  const source = $('sources'); const paths = Object.keys(run?.sources || {});
  if (JSON.stringify(paths) !== source.dataset.paths) {
    const previous = source.value; source.replaceChildren(...paths.map(path => { const option = text('option', path.replace(snapshot.project, '').replace(/^[\\/]/, '')); option.value = path; return option; }));
    if (paths.includes(previous)) source.value = previous; source.dataset.paths = JSON.stringify(paths);
  }
  if ($('follow').checked && run?.active && paths.includes(run.current_path)) source.value = run.current_path;
  renderCode(run);
  const output = $('output'); if (output.textContent !== (run?.output || '')) { const follow = output.scrollHeight - output.scrollTop - output.clientHeight < 30; output.textContent = run?.output || ''; if (follow) output.scrollTop = output.scrollHeight; }
  renderPrompt(run);
  const unavailable = Object.entries(snapshot.capabilities).filter(([_, value]) => value === false).map(([name]) => name);
  $('capabilities').textContent = `One running procedure; up to ${snapshot.capabilities.maxInstances} live instances. Unavailable in this backend: ${unavailable.join(', ')}.`;
}
function renderCode(run) {
  const path = $('sources').value; const content = run?.sources[path] || '';
  const rows = run?.results[path] || {}; const line = run?.active ? run.current[path] : null;
  const key = JSON.stringify([run?.id, path, content, rows, line, run?.status]); if (renderKey === key) return; renderKey = key;
  const fragment = document.createDocumentFragment(); const lines = content.split(/\r?\n/); if (lines.at(-1) === '') lines.pop();
  lines.forEach((source, index) => {
    const number = index + 1, row = rows[number] || {}, tr = document.createElement('tr'); tr.dataset.line = number;
    tr.style.background = number === line ? snapshot.colors.current : snapshot.colors.procedure[run?.status] || '#fff'; tr.style.color = number === line ? '#fff' : '#000';
    for (const value of [number, source, row.timestamp, row.item, row.value, row.status]) tr.append(text('td', String(value ?? '').replaceAll('\x04', ' · ')));
    const resultColor = snapshot.colors.result[String(row.status || '').split(' (')[0]];
    if (resultColor) { tr.lastChild.style.background = resultColor; tr.lastChild.style.color = '#000'; }
    tr.ondblclick = () => openInformation(run, path, number); fragment.append(tr);
  });
  $('code').tBodies[0].replaceChildren(fragment);
  if ($('follow').checked && line) $('code').querySelector(`[data-line="${line}"]`)?.scrollIntoView({block: 'nearest'});
}
function renderPrompt(run) {
  const prompt = run?.active ? run.prompt : null; $('prompt').hidden = !prompt;
  if (!prompt) { promptKey = ''; $('answers').replaceChildren(); pendingAnswer = false; return; }
  const identity = run.id + ':' + prompt.promptId;
  if (identity !== promptKey) {
    promptKey = identity; pendingAnswer = false; $('answers').replaceChildren();
    $('question').textContent = prompt.text; $('prompt-message').textContent = '';
    if (prompt.choices?.length) {
      for (const choice of prompt.choices) {
        const label = document.createElement('label'), input = document.createElement('input'); input.type = 'radio'; input.name = 'answer'; input.value = choice.value; input.required = true;
        label.append(input, text('span', choice.label || '(empty value)')); $('answers').append(label);
      }
    } else {
      const input = document.createElement('input'); input.name = 'answer'; input.type = prompt.inputType === 'password' ? 'password' : 'text';
      input.autocomplete = 'off'; input.setAttribute('aria-label', 'Procedure prompt answer');
      if (prompt.inputType === 'number') input.pattern = '[+-]?(?:[0-9]+(?:\\.[0-9]*)?|\\.[0-9]+)(?:[eE][+-]?[0-9]+)?';
      input.placeholder = prompt.inputType === 'date' ? '17-Oct-2026 14:30:00' : 'Enter your answer'; $('answers').append(input);
    }
    $('hint').textContent = prompt.defaultHint === undefined ? '' : 'Procedure default: ' + prompt.defaultHint;
  }
  const enabled = canControl(run) && !pendingAnswer;
  for (const input of $('answers').querySelectorAll('input')) input.disabled = !enabled;
  $('commit').disabled = $('reset').disabled = !enabled; $('abort-prompt').disabled = !canControl(run);
  if (!run.controlling) $('prompt-message').textContent = 'Monitoring: only the controller can answer.';
}
async function command(command, arguments_ = {threadId: 1}) {
  const run = current(); if (!run || !canControl(run)) return;
  try { error(''); await api('/api/command', {id: run.id, command, arguments: arguments_}); await refresh(); } catch (failure) { error(failure); }
}
$('login').onsubmit = async event => {
  event.preventDefault(); const form = new FormData(event.target);
  try {
    error(''); const result = await api('/api/connect', {name: form.get('name')}, String(form.get('key'))); token = result.client;
    $('login').hidden = true; $('workspace').hidden = false; $('login').elements.key.value = '';
    $('files').replaceChildren(...(await api('/api/files')).map(path => { const option = text('option', path); option.value = path; return option; })); await refresh();
  } catch (failure) { error(failure); }
};
$('disconnect').onclick = async () => { try { await api('/api/disconnect', {}); } catch (failure) { error(failure); } token = ''; connected = false; $('workspace').hidden = true; $('login').hidden = false; $('connection').textContent = 'Disconnected'; };
$('run-form').onsubmit = async event => {
  event.preventDefault(); $('run').disabled = true;
  try { error(''); const result = await api('/api/run', {script: $('files').value, interpreter: $('interpreter').value || undefined, noDebug: !$('debug').checked, stopOnEntry: $('debug').checked}); selected = result.id; $('launcher').open = false; await refresh(); } catch (failure) { error(failure); }
};
for (const button of document.querySelectorAll('[data-command]')) button.onclick = () => command(button.dataset.command, button.dataset.command === 'disconnect' ? {terminateDebuggee: true} : {threadId: 1});
for (const name of ['claim', 'release']) $(name).onclick = async () => { try { await api('/api/control', {id: selected, release: name === 'release'}); await refresh(); } catch (failure) { error(failure); } };
$('prompt').onsubmit = async event => {
  event.preventDefault(); const run = current(); if (!canControl(run) || !run.prompt || pendingAnswer) return;
  const identifier = run.prompt.promptId; const answer = new FormData(event.target).get('answer'); pendingAnswer = true; renderPrompt(run);
  try { await api('/api/command', {id: run.id, command: 'spell/promptAnswer', arguments: {promptId: identifier, value: answer}}); await refresh(); }
  catch (failure) { pendingAnswer = false; $('prompt-message').textContent = failure.message; renderPrompt(run); }
};
$('abort-prompt').onclick = () => command('disconnect', {terminateDebuggee: true});
$('refresh').onclick = refresh; $('sources').onchange = () => { $('follow').checked = false; renderCode(current()); }; $('follow').onchange = () => { renderKey = ''; render(); };
async function openInformation(run, path, line) {
  information = {id: run.id, path, line, after: 0, entries: []}; $('information-title').textContent = `${path.split(/[\\/]/).pop()}:${line} — Item information`;
  $('information').showModal(); await moreInformation();
}
async function moreInformation() {
  if (!information) return; const request = information;
  try { const entries = await api('/api/events?' + new URLSearchParams({id: request.id, path: request.path, line: request.line, after: request.after, latest: $('information-mode').value === 'Latest information'}));
    if (information !== request) return; request.entries.push(...entries); if (entries.length) request.after = entries.at(-1).sequence;
    $('information-more').disabled = entries.length < 500; renderInformation();
  } catch (failure) { error(failure); }
}
function renderInformation() {
  if (!information) return;
  const mode = $('information-mode').value, entries = information.entries, merged = new Map(); let latest = 0;
  for (const entry of entries) { const event = entry.event; latest = Math.max(latest, entry.iteration); if (!event.item && !event.value && !event.status) continue;
    const details = event.details || {}, fields = [event.item, event.value, event.status].map(value => String(value || '').split('\x04'));
    for (let index = 0; index < Math.max(...fields.map(parts => parts.length)); index++) {
      const [name, value, status] = fields.map((parts, field) => parts[index] ?? (field === 2 && parts.length === 1 ? parts[0] : ''));
      const key = JSON.stringify([entry.iteration, event.procedureId, name, details.ItemType]);
      merged.set(key, [entry.iteration, name, value, status, event.timestamp, details.Csp || details.Stack, details.ItemReason || details.Comments]);
    } }
  $('information-count').textContent = `${entries.length} recorded notifications loaded. ${$('information-more').disabled ? '' : 'Load more to inspect later iterations.'}`;
  $('information-raw').hidden = mode !== 'Full'; $('information-table').hidden = mode === 'Full'; $('information-raw').textContent = mode === 'Full' ? JSON.stringify(entries, null, 2) : '';
  const header = document.createElement('tr'); for (const name of ['EX', 'Name', 'Value', 'Status', 'Updated', 'Stack', 'Comments']) header.append(text('th', name)); $('information-table').replaceChildren(header);
  for (const values of merged.values()) { if (mode === 'Latest information' && values[0] !== latest) continue; const row = document.createElement('tr'); for (const value of values) row.append(text('td', String(value ?? '').replaceAll('\x04', ' · '))); $('information-table').append(row); }
}
$('information-more').onclick = moreInformation; $('information-mode').onchange = () => { if (information) { information = {...information, entries: [], after: 0}; moreInformation(); } }; $('information-close').onclick = () => $('information').close();
$('export').onclick = async () => {
  const run = current(); if (!run) return;
  const button = $('export'); button.disabled = true;
  try {
    // Stream to the chosen file when supported; other browsers use a Blob.
    const name = run.script.split(/[\\/]/).pop().replace(/\.py$/, '') + '-' + run.id.slice(0, 8) + '.jsonl';
    const handle = window.showSaveFilePicker ? await window.showSaveFilePicker({suggestedName: name}) : null;
    const record = await api('/api/record?' + new URLSearchParams({id: run.id}));
    const stream = handle ? await handle.createWritable() : null, chunks = []; let after = 0;
    const write = async value => { const line = JSON.stringify(value) + '\n'; if (stream) await stream.write(line); else chunks.push(line); };
    try {
      await write(record);
      for (;;) {
        const entries = await api('/api/events?' + new URLSearchParams({id: run.id, after, until: record.snapshot.last_sequence}));
        for (const entry of entries) await write(entry);
        if (entries.length < 500) break; after = entries.at(-1).sequence;
      }
      if (stream) await stream.close();
      else { const url = URL.createObjectURL(new Blob(chunks, {type: 'application/x-ndjson'})); const link = document.createElement('a'); link.href = url; link.download = name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
    } catch (failure) { if (stream) await stream.abort(); throw failure; }
  } catch (failure) { if (failure.name !== 'AbortError') error(failure); }
  finally { button.disabled = false; }
};
const fragment = new URLSearchParams(location.hash.slice(1)); if (fragment.has('key')) { $('login').elements.key.value = fragment.get('key'); history.replaceState(null, '', location.pathname); }
setInterval(refresh, 750);
