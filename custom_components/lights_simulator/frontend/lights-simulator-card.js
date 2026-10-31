// Lights Simulator — carte Lovelace compacte (type: custom:lights-simulator-card).

const LS_MODES = [["Arrêt", "Arrêt"], ["Auto", "Auto"], ["Forcé", "Forcé"]];
const lsEsc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

class LightsSimulatorCard extends HTMLElement {
  setConfig(config) {
    this._config = { prefixe: "lights_simulator", titre: "Lights Simulator", ...config };
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.addEventListener("click", (e) => this._clic(e));
    }
  }

  static getStubConfig() {
    return {};
  }

  getCardSize() {
    return 5;
  }

  set hass(hass) {
    this._hass = hass;
    const p = this._config.prefixe;
    const ids = ["select", "sensor.etat", "sensor.demarrage", "sensor.lampes_allumees", "sensor.derniere_action",
      "sensor.lever_du_soleil", "sensor.coucher_du_soleil", "binary_sensor.actif"];
    const signature = ids.map((i) => this._etat(i)?.last_updated).join("|");
    if (signature !== this._signature) {
      this._signature = signature;
      this._dessiner();
    }
  }

  _id(nom) {
    const p = this._config.prefixe;
    if (nom === "select") return `select.${p}_mode`;
    const [domaine, cle] = nom.split(".");
    return `${domaine}.${p}_${cle}`;
  }

  _etat(nom) {
    return this._hass?.states[this._id(nom)];
  }

  _texte(nom, defaut = "—") {
    const e = this._etat(nom);
    return e && !["unknown", "unavailable"].includes(e.state) ? e.state : defaut;
  }

  // « 07:34 · demain 07:36 » → « demain 07:36 » : la carte n'affiche que le prochain
  _prochain(nom) {
    const t = this._texte(nom);
    const i = t.indexOf(" · ");
    return i >= 0 ? t.slice(i + 3) : t;
  }

  _clic(e) {
    const cible = e.target.closest("[data-action]");
    if (!cible) return;
    if (cible.dataset.action === "mode") {
      this._hass.callService("select", "select_option", { entity_id: this._id("select"), option: cible.dataset.valeur });
    } else if (cible.dataset.action === "reglages") {
      history.pushState(null, "", "/lights-simulator");
      window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
    }
  }

  _dessiner() {
    if (!this.shadowRoot || !this._hass) return;
    const mode = this._etat("select");
    if (!mode) {
      this.shadowRoot.innerHTML = `<ha-card><div style="padding:16px">Entités Lights Simulator introuvables (préfixe « ${lsEsc(this._config.prefixe)} »).</div></ha-card>`;
      return;
    }
    const actif = this._texte("binary_sensor.actif") === "on";
    this.shadowRoot.innerHTML = `
      <style>
        ha-card { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
        .tete { display: flex; align-items: center; gap: 12px; }
        .icone { width: 44px; height: 44px; border-radius: 22px; display: flex; align-items: center; justify-content: center; background: ${actif ? "#ffe0b2" : "#e1f5fe"}; color: ${actif ? "#6d3a00" : "#01579b"}; }
        h2 { margin: 0; font-size: 16px; font-weight: 500; } .k { color: var(--secondary-text-color); font-size: 13px; }
        .seg { display: flex; border: 1px solid var(--divider-color, #bdbdbd); border-radius: 8px; overflow: hidden; }
        .seg button { flex: 1; border: 0; background: transparent; color: var(--primary-text-color); min-height: 44px; font-family: inherit; font-size: 13px; font-weight: 500; cursor: pointer; }
        .seg button.on { background: var(--primary-color, #0277bd); color: #fff; }
        .row { display: flex; justify-content: space-between; gap: 12px; padding: 8px 0; border-top: 1px solid var(--divider-color, #eee); font-size: 14px; }
        .row span:last-child { text-align: right; }
        .lien { align-self: flex-end; min-height: 44px; padding: 0 14px; border-radius: 8px; border: 1px solid var(--divider-color, #bdbdbd); background: transparent; color: var(--primary-color); font-family: inherit; font-size: 14px; font-weight: 500; cursor: pointer; }
      </style>
      <ha-card>
        <div class="tete">
          <div class="icone"><ha-icon icon="mdi:home-lightbulb"></ha-icon></div>
          <div><h2>${lsEsc(this._config.titre)}</h2><div class="k">${lsEsc(this._texte("sensor.etat"))}</div></div>
        </div>
        <div class="seg" role="group" aria-label="Mode">${LS_MODES.map(([v, l]) =>
          `<button type="button" class="${mode.state === v ? "on" : ""}" aria-pressed="${mode.state === v}" data-action="mode" data-valeur="${lsEsc(v)}">${l}</button>`).join("")}</div>
        <div>
          <div class="row"><span class="k">Démarrage</span><span>${lsEsc(this._texte("sensor.demarrage"))}</span></div>
          <div class="row"><span class="k">Soleil</span><span>lever ${lsEsc(this._prochain("sensor.lever_du_soleil"))} · coucher ${lsEsc(this._prochain("sensor.coucher_du_soleil"))}</span></div>
          <div class="row"><span class="k">Lampes allumées</span><span>${lsEsc(this._texte("sensor.lampes_allumees", "Aucune"))}</span></div>
          <div class="row"><span class="k">Dernière action</span><span>${lsEsc(this._texte("sensor.derniere_action"))}</span></div>
        </div>
        ${this._hass.user?.is_admin ? `<button type="button" class="lien" data-action="reglages">Ouvrir les réglages</button>` : ""}
      </ha-card>`;
  }
}

// Le script est chargé dès l'ouverture de la page, souvent avant que Home Assistant
// n'installe son propre registre d'éléments : une définition faite trop tôt serait
// perdue. On attend donc que l'application soit définie avant d'enregistrer la carte.
const lsDefinir = () => {
  const registre = window.customElements;
  if (registre.get("lights-simulator-card")) return;
  registre.define("lights-simulator-card", LightsSimulatorCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "lights-simulator-card",
    name: "Lights Simulator",
    description: "Mode, état, démarrage et lampes allumées du simulateur de présence.",
  });
};
if (window.customElements.get("home-assistant")) {
  lsDefinir();
} else {
  window.customElements.whenDefined("home-assistant").then(lsDefinir);
}
