class TtlockBlePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._narrow = false;
    this._panel = null;
    this._route = null;
    this._loading = false;
    this._locks = [];
    this._message = "";
    this._error = "";
    this._dialogOpen = false;
    this._submitting = false;
    this._formMode = "add";
    this._activeLockId = null;
    this._form = this._defaultForm();
  }

  set hass(value) {
    this._hass = value;
    if (this._locks.length === 0 && !this._loading) {
      this._bootstrap();
    } else {
      this._render();
    }
  }

  set narrow(value) {
    this._narrow = value;
    this._render();
  }

  set panel(value) {
    this._panel = value;
    this._render();
  }

  set route(value) {
    this._route = value;
    this._render();
  }

  connectedCallback() {
    this._render();
  }

  _defaultForm() {
    return {
      oldCode: "",
      code: "",
      type: "period",
      startDate: "0001311400",
      endDate: "9912311400",
    };
  }

  async _bootstrap() {
    if (!this._hass || this._loading) {
      return;
    }
    this._loading = true;
    this._error = "";
    this._message = "";
    this._render();
    try {
      await this._loadLocks();
      await this._refreshAllLocks();
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
    const batteryEntry = items.find((entry) => entry.tk === "battery");
    const name =
      this._friendlyName(lockEntry?.ei) ||
      this._friendlyName(passcodesEntry?.ei)?.replace(/\s+Passcodes$/i, "") ||
      lockEntry?.en ||
      passcodesEntry?.en ||
      id;
    const passcodeState = passcodesEntry ? this._hass.states[passcodesEntry.ei] : null;
    const batteryState = batteryEntry ? this._hass.states[batteryEntry.ei] : null;
    return {
      id,
      name,
      target: name,
      lockEntityId: lockEntry?.ei || null,
      passcodesEntityId: passcodesEntry?.ei || null,
      batteryEntityId: batteryEntry?.ei || null,
      passcodes: Array.isArray(passcodeState?.attributes?.passcodes)
        ? passcodeState.attributes.passcodes
        : [],
      battery: batteryState?.state || null,
      busy: false,
    };
  }

  _friendlyName(entityId) {
    return entityId ? this._hass.states[entityId]?.attributes?.friendly_name || null : null;
  }

  async _refreshAllLocks() {
    for (const lock of this._locks) {
      await this._refreshLock(lock);
    }
  }

  async _refreshLock(lock) {
    this._setLockBusy(lock.id, true);
    try {
      const result = await this._callService("list_passcodes", {
        lock_mac: lock.target,
      });
      lock.passcodes = result?.response?.passcodes || [];
      this._message = `Passcodes refreshed for ${lock.name}`;
      this._error = "";
    } catch (err) {
      this._error = this._errorText(err);
    } finally {
      this._setLockBusy(lock.id, false);
      this._render();
    }
  }

  _setLockBusy(lockId, busy) {
    const lock = this._locks.find((item) => item.id === lockId);
    if (!lock) {
      return;
    }
    lock.busy = busy;
    this._render();
  }

  async _callService(service, serviceData) {
    return this._hass.connection.sendMessagePromise({
      type: "call_service",
      domain: "ttlock_ble",
      service,
      service_data: serviceData,
      return_response: true,
    });
  }

  _openAddDialog(lock) {
    this._formMode = "add";
    this._activeLockId = lock.id;
    this._form = this._defaultForm();
    this._dialogOpen = true;
    this._message = "";
    this._error = "";
    this._render();
    this.shadowRoot.querySelector("dialog")?.showModal();
  }

  _openEditDialog(lock, passcode) {
    this._formMode = "edit";
    this._activeLockId = lock.id;
    this._form = {
      oldCode: passcode.code || "",
      code: passcode.code || "",
      type: passcode.type === "permanent" ? "permanent" : "period",
      startDate: this._serviceDate(passcode.start_date, "0001311400"),
      endDate: this._serviceDate(passcode.end_date, "9912311400"),
    };
    this._dialogOpen = true;
    this._message = "";
    this._error = "";
    this._render();
    this.shadowRoot.querySelector("dialog")?.showModal();
  }

  _closeDialog() {
    this._dialogOpen = false;
    this._submitting = false;
    this.shadowRoot.querySelector("dialog")?.close();
    this._render();
  }

  _serviceDate(value, fallback) {
    if (!value) {
      return fallback;
    }
    const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(value);
    if (!match) {
      return fallback;
    }
    return `${match[1]}${match[2]}${match[3]}${match[4]}${match[5]}`;
  }

  async _submitDialog() {
    const lock = this._locks.find((item) => item.id === this._activeLockId);
    if (!lock) {
      return;
    }

    const code = this._form.code.trim();
    const oldCode = this._form.oldCode.trim();
    const startDate = this._form.startDate.trim();
    const endDate = this._form.endDate.trim();
    const type = this._form.type;

    if (!/^\d{4,9}$/.test(code)) {
      this._error = "Passcode must be 4-9 digits";
      this._render();
      return;
    }
    if (this._formMode === "edit" && !/^\d{4,9}$/.test(oldCode)) {
      this._error = "Original passcode must be 4-9 digits";
      this._render();
      return;
    }
    if (!/^\d{10}(\d{2})?$/.test(startDate) || !/^\d{10}(\d{2})?$/.test(endDate)) {
      this._error = "Dates must be YYMMDDHHmm or YYYYMMDDHHmm";
      this._render();
      return;
    }

    this._submitting = true;
    this._error = "";
    this._message = "";
    this._render();

    try {
      if (this._formMode === "add") {
        await this._callService("add_passcode", {
          lock_mac: lock.target,
          passcode: code,
          passcode_type: type,
          start_date: startDate,
          end_date: endDate,
        });
        this._message = `Passcode added for ${lock.name}`;
      } else {
        await this._callService("update_passcode", {
          lock_mac: lock.target,
          old_passcode: oldCode,
          new_passcode: code,
          passcode_type: type,
          start_date: startDate,
          end_date: endDate,
        });
        this._message = `Passcode updated for ${lock.name}`;
      }
      await this._refreshLock(lock);
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
    this._message = "";
    this._error = "";
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
    this._render();
  }

  async _clearPasscodes(lock) {
    if (!window.confirm(`Delete all passcodes from ${lock.name}?`)) {
      return;
    }
    this._setLockBusy(lock.id, true);
    this._message = "";
    this._error = "";
    try {
      await this._callService("clear_passcodes", {
        lock_mac: lock.target,
      });
      await this._refreshLock(lock);
      this._message = `All passcodes cleared for ${lock.name}`;
    } catch (err) {
      this._error = this._errorText(err);
      this._setLockBusy(lock.id, false);
    }
    this._render();
  }

  _errorText(err) {
    if (!err) {
      return "Unknown error";
    }
    if (typeof err === "string") {
      return err;
    }
    if (err.body?.message) {
      return err.body.message;
    }
    if (err.error?.message) {
      return err.error.message;
    }
    if (err.message) {
      return err.message;
    }
    return String(err);
  }

  _onFormInput(event) {
    const target = event.currentTarget;
    this._form = {
      ...this._form,
      [target.name]: target.value,
    };
  }

  _renderPasscodeRow(lock, passcode) {
    const validity = passcode.type === "permanent"
      ? "Permanent"
      : `${passcode.start_date || "?"} → ${passcode.end_date || "?"}`;
    return `
      <tr>
        <td class="mono">${passcode.code || "?"}</td>
        <td>${passcode.type || "unknown"}</td>
        <td class="validity">${validity}</td>
        <td class="actions-cell">
          <button class="secondary" data-action="edit" data-lock-id="${lock.id}" data-code="${passcode.code}">Edit</button>
          <button class="danger" data-action="delete" data-lock-id="${lock.id}" data-code="${passcode.code}">Delete</button>
        </td>
      </tr>
    `;
  }

  _renderLock(lock) {
    const passcodes = Array.isArray(lock.passcodes) ? lock.passcodes : [];
    const rows = passcodes.length
      ? passcodes.map((passcode) => this._renderPasscodeRow(lock, passcode)).join("")
      : `
        <tr>
          <td colspan="4" class="empty">No passcodes loaded yet. Click Refresh.</td>
        </tr>
      `;
    return `
      <section class="lock-card">
        <div class="lock-header">
          <div>
            <h2>${lock.name}</h2>
            <div class="meta">
              ${lock.battery ? `Battery ${lock.battery}%` : "Battery unknown"}
            </div>
          </div>
          <div class="toolbar">
            <button data-action="refresh" data-lock-id="${lock.id}" ${lock.busy ? "disabled" : ""}>Refresh</button>
            <button data-action="add" data-lock-id="${lock.id}" ${lock.busy ? "disabled" : ""}>Add passcode</button>
            <button class="danger" data-action="clear" data-lock-id="${lock.id}" ${lock.busy ? "disabled" : ""}>Clear all</button>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Code</th>
                <th>Type</th>
                <th>Validity</th>
                <th></th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </section>
    `;
  }

  _render() {
    const activeLock = this._locks.find((item) => item.id === this._activeLockId);
    const title = this._panel?.config?.title || "TTLock Manager";
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          min-height: 100%;
          color: var(--primary-text-color);
          background: var(--lovelace-background, var(--primary-background-color));
        }
        .page {
          max-width: 1200px;
          margin: 0 auto;
          padding: 24px 20px 40px;
        }
        .topbar {
          display: flex;
          gap: 16px;
          align-items: flex-start;
          justify-content: space-between;
          margin-bottom: 20px;
          flex-wrap: wrap;
        }
        h1 {
          margin: 0;
          font-size: 28px;
          line-height: 1.2;
          font-weight: 600;
        }
        .subtitle {
          color: var(--secondary-text-color);
          margin-top: 6px;
          font-size: 14px;
        }
        .status {
          margin-bottom: 16px;
          padding: 12px 14px;
          border-radius: 8px;
          font-size: 14px;
        }
        .status.info {
          background: rgba(33, 150, 243, 0.12);
          color: var(--primary-text-color);
        }
        .status.error {
          background: rgba(244, 67, 54, 0.12);
          color: var(--error-color, #db4437);
        }
        .lock-list {
          display: grid;
          gap: 16px;
        }
        .lock-card {
          background: var(--card-background-color);
          border-radius: 8px;
          box-shadow: var(--ha-card-box-shadow, none);
          padding: 18px;
        }
        .lock-header {
          display: flex;
          gap: 12px;
          justify-content: space-between;
          align-items: flex-start;
          margin-bottom: 16px;
          flex-wrap: wrap;
        }
        h2 {
          margin: 0;
          font-size: 20px;
          line-height: 1.3;
        }
        .meta {
          margin-top: 6px;
          color: var(--secondary-text-color);
          font-size: 13px;
        }
        .toolbar {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
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
        button:hover:not(:disabled) {
          border-color: var(--primary-color);
        }
        button:disabled {
          opacity: 0.5;
          cursor: wait;
        }
        button.secondary {
          padding: 6px 10px;
        }
        button.danger {
          color: var(--error-color, #db4437);
        }
        .table-wrap {
          overflow-x: auto;
        }
        table {
          width: 100%;
          border-collapse: collapse;
          min-width: 680px;
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
          letter-spacing: 0;
        }
        .validity {
          word-break: break-word;
        }
        .actions-cell {
          display: flex;
          gap: 8px;
          justify-content: flex-end;
        }
        .empty {
          color: var(--secondary-text-color);
          font-style: italic;
        }
        .loading {
          color: var(--secondary-text-color);
          padding: 24px 0;
        }
        dialog {
          border: 0;
          border-radius: 12px;
          padding: 0;
          width: min(520px, calc(100vw - 24px));
          background: var(--card-background-color);
          color: var(--primary-text-color);
        }
        dialog::backdrop {
          background: rgba(0, 0, 0, 0.45);
        }
        .dialog-body {
          padding: 20px;
        }
        .dialog-title {
          font-size: 20px;
          font-weight: 600;
          margin-bottom: 8px;
        }
        .dialog-subtitle {
          color: var(--secondary-text-color);
          font-size: 14px;
          margin-bottom: 16px;
        }
        .form-grid {
          display: grid;
          gap: 12px;
        }
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
        .dialog-actions {
          display: flex;
          justify-content: flex-end;
          gap: 8px;
          margin-top: 18px;
        }
        @media (max-width: 800px) {
          .page {
            padding: 16px 12px 32px;
          }
          .actions-cell {
            justify-content: flex-start;
          }
          table {
            min-width: 560px;
          }
        }
      </style>
      <div class="page">
        <div class="topbar">
          <div>
            <h1>${title}</h1>
            <div class="subtitle">Manage TTLock passcodes with an actual form instead of raw service calls.</div>
          </div>
          <div class="toolbar">
            <button id="refresh-all" ${this._loading ? "disabled" : ""}>Refresh all</button>
          </div>
        </div>
        ${this._message ? `<div class="status info">${this._message}</div>` : ""}
        ${this._error ? `<div class="status error">${this._error}</div>` : ""}
        ${
          this._loading && this._locks.length === 0
            ? `<div class="loading">Loading TTLock devices…</div>`
            : `<div class="lock-list">${this._locks.map((lock) => this._renderLock(lock)).join("") || `<div class="loading">No TTLock BLE locks found.</div>`}</div>`
        }
        <dialog>
          <div class="dialog-body">
            <div class="dialog-title">${this._formMode === "add" ? "Add passcode" : "Edit passcode"}</div>
            <div class="dialog-subtitle">${activeLock ? activeLock.name : ""}</div>
            <div class="form-grid">
              ${
                this._formMode === "edit"
                  ? `
                    <label>
                      Original code
                      <input name="oldCode" value="${this._form.oldCode}" disabled />
                    </label>
                  `
                  : ""
              }
              <label>
                Passcode
                <input name="code" value="${this._form.code}" inputmode="numeric" autocomplete="off" />
              </label>
              <label>
                Type
                <select name="type">
                  <option value="period" ${this._form.type === "period" ? "selected" : ""}>Period</option>
                  <option value="permanent" ${this._form.type === "permanent" ? "selected" : ""}>Permanent</option>
                </select>
              </label>
              <label>
                Start date
                <input name="startDate" value="${this._form.startDate}" autocomplete="off" />
              </label>
              <label>
                End date
                <input name="endDate" value="${this._form.endDate}" autocomplete="off" />
              </label>
            </div>
            <div class="dialog-actions">
              <button id="cancel-dialog" ${this._submitting ? "disabled" : ""}>Cancel</button>
              <button id="submit-dialog" ${this._submitting ? "disabled" : ""}>${this._submitting ? "Saving…" : "Save"}</button>
            </div>
          </div>
        </dialog>
      </div>
    `;

    this.shadowRoot.getElementById("refresh-all")?.addEventListener("click", () => {
      this._bootstrap();
    });

    this.shadowRoot.querySelectorAll("[data-action]").forEach((button) => {
      button.addEventListener("click", async (event) => {
        const action = event.currentTarget.dataset.action;
        const lock = this._locks.find((item) => item.id === event.currentTarget.dataset.lockId);
        if (!lock) {
          return;
        }
        if (action === "refresh") {
          await this._refreshLock(lock);
          return;
        }
        if (action === "add") {
          this._openAddDialog(lock);
          return;
        }
        if (action === "clear") {
          await this._clearPasscodes(lock);
          return;
        }
        const passcode = lock.passcodes.find((item) => item.code === event.currentTarget.dataset.code);
        if (!passcode) {
          return;
        }
        if (action === "edit") {
          this._openEditDialog(lock, passcode);
          return;
        }
        if (action === "delete") {
          await this._deletePasscode(lock, passcode);
        }
      });
    });

    if (this._dialogOpen) {
      this.shadowRoot.querySelectorAll("input, select").forEach((input) => {
        input.addEventListener("input", (event) => this._onFormInput(event));
        input.addEventListener("change", (event) => this._onFormInput(event));
      });
      this.shadowRoot.getElementById("cancel-dialog")?.addEventListener("click", () => this._closeDialog());
      this.shadowRoot.getElementById("submit-dialog")?.addEventListener("click", () => this._submitDialog());
      this.shadowRoot.querySelector("dialog")?.addEventListener("cancel", (event) => {
        event.preventDefault();
        this._closeDialog();
      });
      const dialog = this.shadowRoot.querySelector("dialog");
      if (dialog && !dialog.open) {
        dialog.showModal();
      }
    }
  }
}

customElements.define("ttlock-ble-panel", TtlockBlePanel);
