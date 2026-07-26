class TtlockBlePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._loading = false;
    this._locks = [];
    this._message = "";
    this._error = "";
    this._dialogOpen = false;
    this._submitting = false;
    this._dialogKind = "passcode-add";
    this._activeLockId = null;
    this._form = this._defaultForm();
  }

  set hass(value) {
    this._hass = value;
    if (!this._loading && this._locks.length === 0) {
      this._bootstrap();
      return;
    }
    this._render();
  }

  set narrow(_value) {}
  set panel(value) {
    this._panel = value;
    this._render();
  }
  set route(_value) {}

  connectedCallback() {
    this._render();
  }

  _defaultForm() {
    const now = new Date();
    const later = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000);
    return {
      code: "",
      oldCode: "",
      label: "",
      type: "period",
      startAt: this._toDateTimeLocal(now),
      endAt: this._toDateTimeLocal(later),
    };
  }

  async _bootstrap() {
    if (!this._hass || this._loading) {
      return;
    }
    this._loading = true;
    this._message = "";
    this._error = "";
    this._render();
    try {
      await this._loadLocks();
      await this._refreshAll();
    } catch (err) {
      this._error = this._errorText(err);
    } finally {
      this._loading = false;
      this._render();
    }
  }

  async _loadLocks() {
    const registry = await this._hass.connection.sendMessagePromise({
      type: "config/entity_registry/list_for_display",
    });
    const entries = registry.entities.filter((entry) => entry.pl === "ttlock_ble");
    const grouped = new Map();

    for (const entry of entries) {
      const key = entry.di || entry.ei;
      if (!grouped.has(key)) {
        grouped.set(key, []);
      }
      grouped.get(key).push(entry);
    }

    this._locks = Array.from(grouped.entries())
      .map(([id, items]) => this._buildLock(id, items))
      .filter(Boolean)
      .sort((a, b) => a.name.localeCompare(b.name));
  }

  _buildLock(id, items) {
    const lockEntry = items.find((entry) => entry.ei.startsWith("lock."));
    const passcodesEntry = items.find((entry) => entry.tk === "passcodes_count");
    const fingerprintsEntry = items.find((entry) => entry.tk === "fingerprints_count");
    const batteryEntry = items.find((entry) => entry.tk === "battery");
    const lockEntityId = lockEntry?.ei || passcodesEntry?.ei || fingerprintsEntry?.ei || null;
    const name =
      this._friendlyName(lockEntityId) ||
      lockEntry?.en ||
      passcodesEntry?.en ||
      fingerprintsEntry?.en ||
      id;

    return {
      id,
      name: name.replace(/\s+(Lock|Passcodes|Fingerprints)$/i, ""),
      target: lockEntityId || name,
      busy: false,
      battery: batteryEntry ? this._hass.states[batteryEntry.ei]?.state || null : null,
      passcodes: [],
      fingerprints: [],
      history: [],
      passcodesError: "",
      fingerprintsError: "",
      historyError: "",
    };
  }

  _friendlyName(entityId) {
    return entityId ? this._hass.states[entityId]?.attributes?.friendly_name || null : null;
  }

  _setLockBusy(lockId, busy) {
    const lock = this._locks.find((item) => item.id === lockId);
    if (!lock) {
      return;
    }
    lock.busy = busy;
    this._render();
  }

  async _callService(service, serviceData, { returnResponse = false } = {}) {
    const message = {
      type: "call_service",
      domain: "ttlock_ble",
      service,
      service_data: serviceData,
    };
    if (returnResponse) {
      message.return_response = true;
    }
    return this._hass.connection.sendMessagePromise(message);
  }

  async _refreshAll() {
    for (const lock of this._locks) {
      await this._refreshLock(lock);
    }
  }

  async _refreshLock(lock) {
    this._setLockBusy(lock.id, true);
    try {
      const [passcodesResult, fingerprintsResult, historyResult] = await Promise.allSettled([
        this._callService("list_passcodes", { lock_mac: lock.target }, { returnResponse: true }),
        this._callService("list_fingerprints", { lock_mac: lock.target }, { returnResponse: true }),
        this._callService("list_operation_log", { lock_mac: lock.target }, { returnResponse: true }),
      ]);

      if (passcodesResult.status === "fulfilled") {
        lock.passcodes = passcodesResult.value?.response?.passcodes || [];
        lock.passcodesError = passcodesResult.value?.response?.warning || "";
      } else {
        lock.passcodes = [];
        lock.passcodesError = this._errorText(passcodesResult.reason);
      }

      if (fingerprintsResult.status === "fulfilled") {
        lock.fingerprints = fingerprintsResult.value?.response?.fingerprints || [];
        lock.fingerprintsError = "";
      } else {
        lock.fingerprints = [];
        lock.fingerprintsError = this._errorText(fingerprintsResult.reason);
      }

      if (historyResult.status === "fulfilled") {
        lock.history = historyResult.value?.response?.entries || [];
        lock.historyError = "";
      } else {
        lock.history = [];
        lock.historyError = this._errorText(historyResult.reason);
      }

      this._message =
        lock.passcodesError || lock.fingerprintsError || lock.historyError
          ? `Updated ${lock.name} with partial data`
          : `Updated ${lock.name}`;
      this._error = "";
    } catch (err) {
      this._error = this._errorText(err);
    } finally {
      this._setLockBusy(lock.id, false);
      this._render();
    }
  }

  _errorText(err) {
    if (!err) return "Unknown error";
    if (typeof err === "string") return err;
    if (err.body?.message) return err.body.message;
    if (err.error?.message) return err.error.message;
    if (err.message) return err.message;
    return String(err);
  }

  _toDateTimeLocal(value) {
    const date = value instanceof Date ? value : new Date(value);
    const pad = (num) => String(num).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }

  _serviceDateFromLocal(value, fallback) {
    if (!value) {
      return fallback;
    }
    const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
    if (!match) {
      return fallback;
    }
    return `${match[1]}${match[2]}${match[3]}${match[4]}${match[5]}`;
  }

  _displayDate(value) {
    if (!value) {
      return "—";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value;
    }
    return date.toLocaleString();
  }

  _openPasscodeDialog(lock, passcode = null) {
    const now = new Date();
    const later = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000);
    this._dialogKind = passcode ? "passcode-edit" : "passcode-add";
    this._activeLockId = lock.id;
    this._form = {
      code: passcode?.code || "",
      oldCode: passcode?.code || "",
      label: passcode?.label || "",
      type: passcode?.type === "permanent" ? "permanent" : "period",
      startAt: passcode?.start_date ? this._toDateTimeLocal(passcode.start_date) : this._toDateTimeLocal(now),
      endAt: passcode?.end_date ? this._toDateTimeLocal(passcode.end_date) : this._toDateTimeLocal(later),
    };
    this._dialogOpen = true;
    this._submitting = false;
    this._message = "";
    this._error = "";
    this._render();
    const dialog = this.shadowRoot.querySelector("dialog");
    if (dialog && !dialog.open) {
      dialog.showModal();
    }
  }

  _closeDialog() {
    this._dialogOpen = false;
    this._submitting = false;
    this.shadowRoot.querySelector("dialog")?.close();
    this._render();
  }

  _onFormInput(event) {
    const { name, value } = event.currentTarget;
    this._form = { ...this._form, [name]: value };
  }

  async _submitDialog() {
    const lock = this._locks.find((item) => item.id === this._activeLockId);
    if (!lock) {
      return;
    }

    const code = this._form.code.trim();
    const oldCode = this._form.oldCode.trim();
    const label = this._form.label.trim();

    if (!/^\d{4,9}$/.test(code)) {
      this._error = "Passcode must be 4-9 digits";
      this._render();
      return;
    }
    if (this._dialogKind === "passcode-edit" && !/^\d{4,9}$/.test(oldCode)) {
      this._error = "Original passcode must be 4-9 digits";
      this._render();
      return;
    }

    this._submitting = true;
    this._error = "";
    this._render();

    try {
      const payload = {
        lock_mac: lock.target,
        passcode_type: this._form.type,
        start_date: this._serviceDateFromLocal(this._form.startAt, "0001311400"),
        end_date: this._serviceDateFromLocal(this._form.endAt, "9912311400"),
      };
      if (this._dialogKind === "passcode-add") {
        await this._callService("add_passcode", { ...payload, passcode: code }, { returnResponse: true });
      } else {
        await this._callService("update_passcode", {
          ...payload,
          old_passcode: oldCode,
          new_passcode: code,
        });
      }
      await this._callService("set_passcode_label", {
        lock_mac: lock.target,
        passcode: code,
        label,
      });
      await this._refreshLock(lock);
      this._message = this._dialogKind === "passcode-add"
        ? `Passcode added for ${lock.name}`
        : `Passcode updated for ${lock.name}`;
      this._closeDialog();
    } catch (err) {
      this._error = this._errorText(err);
      this._submitting = false;
      this._render();
    }
  }

  async _deletePasscode(lock, passcode) {
    if (!window.confirm(`Delete passcode ${passcode.code} from ${lock.name}?`)) {
      return;
    }
    this._setLockBusy(lock.id, true);
    try {
      await this._callService("delete_passcode", {
        lock_mac: lock.target,
        passcode: passcode.code,
        passcode_type: passcode.type === "permanent" ? "permanent" : "period",
      });
      await this._refreshLock(lock);
      this._message = `Passcode deleted from ${lock.name}`;
    } catch (err) {
      this._error = this._errorText(err);
      this._setLockBusy(lock.id, false);
    }
  }

  async _clearPasscodes(lock) {
    if (!window.confirm(`Delete all passcodes from ${lock.name}?`)) {
      return;
    }
    this._setLockBusy(lock.id, true);
    try {
      await this._callService("clear_passcodes", { lock_mac: lock.target });
      await this._refreshLock(lock);
      this._message = `All passcodes cleared for ${lock.name}`;
    } catch (err) {
      this._error = this._errorText(err);
      this._setLockBusy(lock.id, false);
    }
  }

  async _addFingerprint(lock) {
    this._setLockBusy(lock.id, true);
    this._message = `Fingerprint enrollment started on ${lock.name}`;
    this._error = "";
    try {
      const result = await this._callService("add_fingerprint", {
        lock_mac: lock.target,
        start_date: "200001010000",
        end_date: "209912312359",
        scan_timeout: 45,
      }, { returnResponse: true });
      const fingerprint = result?.response?.fingerprint;
      if (fingerprint?.fingerprint_number) {
        const label = window.prompt(
          `Fingerprint ${fingerprint.fingerprint_number} added. Enter owner label:`,
          "",
        );
        if (label !== null) {
          await this._callService("set_fingerprint_label", {
            lock_mac: lock.target,
            fingerprint_number: fingerprint.fingerprint_number,
            label,
          });
        }
      }
      await this._refreshLock(lock);
    } catch (err) {
      this._error = this._errorText(err);
      this._setLockBusy(lock.id, false);
    }
  }

  async _editFingerprintLabel(lock, fingerprint) {
    const label = window.prompt(
      `Set owner label for fingerprint ${fingerprint.fingerprint_number}:`,
      fingerprint.label || "",
    );
    if (label === null) {
      return;
    }
    this._setLockBusy(lock.id, true);
    try {
      await this._callService("set_fingerprint_label", {
        lock_mac: lock.target,
        fingerprint_number: fingerprint.fingerprint_number,
        label,
      });
      await this._refreshLock(lock);
    } catch (err) {
      this._error = this._errorText(err);
      this._setLockBusy(lock.id, false);
    }
  }

  async _deleteFingerprint(lock, fingerprint) {
    if (!window.confirm(`Delete fingerprint ${fingerprint.fingerprint_number} from ${lock.name}?`)) {
      return;
    }
    this._setLockBusy(lock.id, true);
    try {
      await this._callService("delete_fingerprint", {
        lock_mac: lock.target,
        fingerprint_number: fingerprint.fingerprint_number,
      });
      await this._refreshLock(lock);
      this._message = `Fingerprint deleted from ${lock.name}`;
    } catch (err) {
      this._error = this._errorText(err);
      this._setLockBusy(lock.id, false);
    }
  }

  _renderPasscodes(lock) {
    const rows = lock.passcodes.length
      ? lock.passcodes.map((passcode) => `
          <tr>
            <td class="mono">${passcode.code || "?"}</td>
            <td>${passcode.label || "—"}</td>
            <td>${passcode.type || "unknown"}</td>
            <td>${passcode.type === "permanent" ? "Permanent" : `${this._displayDate(passcode.start_date)} → ${this._displayDate(passcode.end_date)}`}</td>
            <td class="actions">
              <button data-action="edit-passcode" data-lock-id="${lock.id}" data-code="${passcode.code}">Edit</button>
              <button class="danger" data-action="delete-passcode" data-lock-id="${lock.id}" data-code="${passcode.code}">Delete</button>
            </td>
          </tr>
        `).join("")
      : `<tr><td colspan="5" class="empty">No passcodes yet.</td></tr>`;
    const warning = lock.passcodesError
      ? `<div class="section-note error-note">${lock.passcodesError}</div>`
      : "";

    return `
      <section class="section">
        <div class="section-header">
          <h3>Passcodes</h3>
          <div class="toolbar">
            <button data-action="add-passcode" data-lock-id="${lock.id}" ${lock.busy ? "disabled" : ""}>Add passcode</button>
            <button class="danger" data-action="clear-passcodes" data-lock-id="${lock.id}" ${lock.busy ? "disabled" : ""}>Clear all</button>
          </div>
        </div>
        ${warning}
        <div class="table-wrap">
          <table>
            <thead>
              <tr><th>Code</th><th>Owner</th><th>Type</th><th>Validity</th><th></th></tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </section>
    `;
  }

  _renderFingerprints(lock) {
    const rows = lock.fingerprints.length
      ? lock.fingerprints.map((fingerprint) => `
          <tr>
            <td class="mono">${fingerprint.fingerprint_number || "?"}</td>
            <td>${fingerprint.label || "—"}</td>
            <td>${this._displayDate(fingerprint.start_date)}</td>
            <td>${this._displayDate(fingerprint.end_date)}</td>
            <td class="actions">
              <button data-action="edit-fingerprint-label" data-lock-id="${lock.id}" data-fingerprint-number="${fingerprint.fingerprint_number}">Owner</button>
              <button class="danger" data-action="delete-fingerprint" data-lock-id="${lock.id}" data-fingerprint-number="${fingerprint.fingerprint_number}">Delete</button>
            </td>
          </tr>
        `).join("")
      : `<tr><td colspan="5" class="empty">No fingerprints yet.</td></tr>`;
    const warning = lock.fingerprintsError
      ? `<div class="section-note error-note">${lock.fingerprintsError}</div>`
      : "";

    return `
      <section class="section">
        <div class="section-header">
          <h3>Fingerprints</h3>
          <div class="toolbar">
            <button data-action="add-fingerprint" data-lock-id="${lock.id}" ${lock.busy ? "disabled" : ""}>Add fingerprint</button>
          </div>
        </div>
        ${warning}
        <div class="table-wrap">
          <table>
            <thead>
              <tr><th>ID</th><th>Owner</th><th>Start</th><th>End</th><th></th></tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </section>
    `;
  }

  _renderHistory(lock) {
    const entries = lock.history.slice(0, 20);
    const rows = entries.length
      ? entries.map((entry) => `
          <tr>
            <td>${this._displayDate(entry.operate_date)}</td>
            <td>${entry.record_type || "unknown"}</td>
            <td>${entry.password || "—"}</td>
            <td>${entry.lock_battery ?? "—"}%</td>
          </tr>
        `).join("")
      : `<tr><td colspan="4" class="empty">No history loaded.</td></tr>`;
    const warning = lock.historyError
      ? `<div class="section-note error-note">${lock.historyError}</div>`
      : "";

    return `
      <section class="section">
        <div class="section-header">
          <h3>History</h3>
          <div class="toolbar">
            <button data-action="refresh-lock" data-lock-id="${lock.id}" ${lock.busy ? "disabled" : ""}>Refresh history</button>
          </div>
        </div>
        ${warning}
        <div class="table-wrap">
          <table>
            <thead>
              <tr><th>Time</th><th>Action</th><th>Credential</th><th>Battery</th></tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </section>
    `;
  }

  _renderLock(lock) {
    return `
      <article class="lock-card">
        <div class="lock-header">
          <div>
            <h2>${lock.name}</h2>
            <div class="meta">${lock.battery ? `Battery ${lock.battery}%` : "Battery unknown"}</div>
          </div>
          <div class="toolbar">
            <button data-action="refresh-lock" data-lock-id="${lock.id}" ${lock.busy ? "disabled" : ""}>Refresh</button>
          </div>
        </div>
        ${this._renderPasscodes(lock)}
        ${this._renderFingerprints(lock)}
        ${this._renderHistory(lock)}
      </article>
    `;
  }

  _renderDialog() {
    if (!this._dialogOpen) {
      return `<dialog></dialog>`;
    }
    const activeLock = this._locks.find((item) => item.id === this._activeLockId);
    const title = this._dialogKind === "passcode-add" ? "Add passcode" : "Edit passcode";
    return `
      <dialog>
        <div class="dialog-body">
          <div class="dialog-title">${title}</div>
          <div class="dialog-subtitle">${activeLock?.name || ""}</div>
          <div class="form-grid">
            ${this._dialogKind === "passcode-edit" ? `
              <label>
                Original code
                <input value="${this._form.oldCode}" disabled />
              </label>
            ` : ""}
            <label>
              New code
              <input name="code" value="${this._form.code}" inputmode="numeric" autocomplete="off" />
            </label>
            <label>
              Owner
              <input name="label" value="${this._form.label}" autocomplete="off" />
            </label>
            <label>
              Type
              <select name="type">
                <option value="period" ${this._form.type === "period" ? "selected" : ""}>Period</option>
                <option value="permanent" ${this._form.type === "permanent" ? "selected" : ""}>Permanent</option>
              </select>
            </label>
            <label>
              Start
              <input name="startAt" type="datetime-local" value="${this._form.startAt}" />
            </label>
            <label>
              End
              <input name="endAt" type="datetime-local" value="${this._form.endAt}" ${this._form.type === "permanent" ? "disabled" : ""} />
            </label>
          </div>
          <div class="dialog-actions">
            <button id="cancel-dialog" ${this._submitting ? "disabled" : ""}>Cancel</button>
            <button id="submit-dialog" ${this._submitting ? "disabled" : ""}>${this._submitting ? "Saving..." : "Save"}</button>
          </div>
        </div>
      </dialog>
    `;
  }

  _bindEvents() {
    this.shadowRoot.getElementById("refresh-all")?.addEventListener("click", () => this._bootstrap());

    this.shadowRoot.querySelectorAll("[data-action]").forEach((button) => {
      button.addEventListener("click", async (event) => {
        const target = event.currentTarget;
        const action = target.dataset.action;
        const lock = this._locks.find((item) => item.id === target.dataset.lockId);
        if (!lock) return;

        if (action === "refresh-lock") return this._refreshLock(lock);
        if (action === "add-passcode") return this._openPasscodeDialog(lock);
        if (action === "clear-passcodes") return this._clearPasscodes(lock);
        if (action === "add-fingerprint") return this._addFingerprint(lock);

        if (action === "edit-passcode" || action === "delete-passcode") {
          const passcode = lock.passcodes.find((item) => item.code === target.dataset.code);
          if (!passcode) return;
          if (action === "edit-passcode") return this._openPasscodeDialog(lock, passcode);
          return this._deletePasscode(lock, passcode);
        }

        if (action === "edit-fingerprint-label" || action === "delete-fingerprint") {
          const fingerprint = lock.fingerprints.find(
            (item) => item.fingerprint_number === target.dataset.fingerprintNumber,
          );
          if (!fingerprint) return;
          if (action === "edit-fingerprint-label") return this._editFingerprintLabel(lock, fingerprint);
          return this._deleteFingerprint(lock, fingerprint);
        }
      });
    });

    if (this._dialogOpen) {
      this.shadowRoot.querySelectorAll("input[name], select[name]").forEach((input) => {
        input.addEventListener("input", (event) => this._onFormInput(event));
        input.addEventListener("change", (event) => this._onFormInput(event));
      });
      this.shadowRoot.getElementById("cancel-dialog")?.addEventListener("click", () => this._closeDialog());
      this.shadowRoot.getElementById("submit-dialog")?.addEventListener("click", () => this._submitDialog());
      const dialog = this.shadowRoot.querySelector("dialog");
      dialog?.addEventListener("cancel", (event) => {
        event.preventDefault();
        this._closeDialog();
      });
      if (dialog && !dialog.open) {
        dialog.showModal();
      }
    }
  }

  _render() {
    const title = this._panel?.config?.title || "TTLock Manager";
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          min-height: 100%;
          background: var(--lovelace-background, var(--primary-background-color));
          color: var(--primary-text-color);
        }
        .page {
          max-width: 1240px;
          margin: 0 auto;
          padding: 24px 20px 40px;
        }
        .topbar, .lock-header, .section-header, .toolbar, .dialog-actions, .actions {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
        }
        .topbar, .lock-header, .section-header {
          justify-content: space-between;
          align-items: flex-start;
        }
        .topbar {
          margin-bottom: 20px;
        }
        h1, h2, h3 {
          margin: 0;
          letter-spacing: 0;
        }
        h1 { font-size: 28px; line-height: 1.2; }
        h2 { font-size: 20px; line-height: 1.3; }
        h3 { font-size: 16px; line-height: 1.3; }
        .subtitle, .meta {
          color: var(--secondary-text-color);
          font-size: 14px;
          margin-top: 6px;
        }
        .status {
          margin-bottom: 16px;
          padding: 12px 14px;
          border-radius: 8px;
          font-size: 14px;
        }
        .info { background: rgba(33, 150, 243, 0.12); }
        .error { background: rgba(244, 67, 54, 0.12); color: var(--error-color, #db4437); }
        .lock-list {
          display: grid;
          gap: 18px;
        }
        .lock-card {
          background: var(--card-background-color);
          border-radius: 8px;
          box-shadow: var(--ha-card-box-shadow, none);
          padding: 18px;
        }
        .section {
          margin-top: 18px;
        }
        button {
          appearance: none;
          border: 1px solid var(--divider-color);
          background: var(--card-background-color);
          color: var(--primary-text-color);
          border-radius: 8px;
          padding: 9px 14px;
          cursor: pointer;
          font: inherit;
        }
        button:hover:not(:disabled) { border-color: var(--primary-color); }
        button:disabled { opacity: 0.55; cursor: wait; }
        .danger { color: var(--error-color, #db4437); }
        .table-wrap { overflow-x: auto; }
        table {
          width: 100%;
          border-collapse: collapse;
          min-width: 720px;
        }
        th, td {
          text-align: left;
          padding: 12px 10px;
          border-top: 1px solid var(--divider-color);
          vertical-align: middle;
          font-size: 14px;
        }
        th {
          color: var(--secondary-text-color);
          font-weight: 500;
          border-top: 0;
          padding-top: 0;
        }
        .mono {
          font-family: ui-monospace, SFMono-Regular, SF Mono, Consolas, monospace;
        }
        .empty {
          color: var(--secondary-text-color);
          font-style: italic;
        }
        .section-note {
          margin: 10px 0 12px;
          padding: 10px 12px;
          border-radius: 8px;
          font-size: 13px;
          background: rgba(255, 152, 0, 0.12);
          color: var(--primary-text-color);
        }
        .error-note {
          background: rgba(244, 67, 54, 0.12);
          color: var(--error-color, #db4437);
        }
        .loading {
          color: var(--secondary-text-color);
          padding: 24px 0;
        }
        dialog {
          border: 0;
          border-radius: 12px;
          padding: 0;
          width: min(560px, calc(100vw - 24px));
          background: var(--card-background-color);
          color: var(--primary-text-color);
        }
        dialog::backdrop {
          background: rgba(0, 0, 0, 0.45);
        }
        .dialog-body { padding: 20px; }
        .dialog-title { font-size: 20px; font-weight: 600; margin-bottom: 8px; }
        .dialog-subtitle { color: var(--secondary-text-color); font-size: 14px; margin-bottom: 16px; }
        .form-grid { display: grid; gap: 12px; }
        label {
          display: grid;
          gap: 6px;
          font-size: 14px;
        }
        input, select {
          width: 100%;
          box-sizing: border-box;
          border: 1px solid var(--divider-color);
          background: var(--secondary-background-color, var(--card-background-color));
          color: var(--primary-text-color);
          border-radius: 8px;
          padding: 10px 12px;
          font: inherit;
        }
        @media (max-width: 800px) {
          .page { padding: 16px 12px 32px; }
          table { min-width: 620px; }
        }
      </style>
      <div class="page">
        <div class="topbar">
          <div>
            <h1>${title}</h1>
            <div class="subtitle">Fingerprints, passcodes, history and sane date pickers in one place.</div>
          </div>
          <div class="toolbar">
            <button id="refresh-all" ${this._loading ? "disabled" : ""}>Refresh all</button>
          </div>
        </div>
        ${this._message ? `<div class="status info">${this._message}</div>` : ""}
        ${this._error ? `<div class="status error">${this._error}</div>` : ""}
        ${
          this._loading && this._locks.length === 0
            ? `<div class="loading">Loading TTLock devices...</div>`
            : `<div class="lock-list">${this._locks.map((lock) => this._renderLock(lock)).join("") || `<div class="loading">No TTLock BLE locks found.</div>`}</div>`
        }
        ${this._renderDialog()}
      </div>
    `;
    this._bindEvents();
  }
}

customElements.define("ttlock-ble-panel", TtlockBlePanel);
