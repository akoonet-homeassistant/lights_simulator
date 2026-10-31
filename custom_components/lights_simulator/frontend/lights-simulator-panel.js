// Lights Simulator — panneau latéral (onglets Fonctionnement, Plages, Lampes, Rythme, Entités, Sauvegarde).

const DOMAINE = "lights_simulator";
const ONGLETS = [
  ["fonctionnement", "Fonctionnement"],
  ["plages", "Plages"],
  ["lampes", "Lampes"],
  ["rythme", "Rythme"],
  ["entites", "Entités"],
  ["sauvegarde", "Sauvegarde"],
];
const JOURS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];
const MODES = [["arret", "Arrêt"], ["auto", "Auto"], ["force", "Forcé"]];
const BORNES = [["soleil", "Soleil"], ["fixe", "Heure fixe"], ["lux", "Luminosité"]];
const DECLENCHEURS = [["alarme", "Alarme"], ["personnes", "Personnes"], ["les_deux", "L'un ou l'autre"]];
const ETATS_ALARME = [
  ["armed_away", "Armée absence"],
  ["armed_night", "Armée nuit"],
  ["armed_home", "Armée présence"],
  ["armed_vacation", "Armée vacances"],
  ["armed_custom_bypass", "Armée personnalisée"],
];
const SI_ECLAIREE = [
  ["autre", "Ne pas allumer, tirer une autre lampe", "Par défaut. Une lampe allumée en plein jour ne trompe personne."],
  ["quand_meme", "Allumer quand même", "Le capteur sert seulement à l'information."],
  ["action", "Lancer une action à la place", "Par exemple fermer le volet de la pièce."],
];

const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const heure = (iso) => {
  try {
    return new Date(iso).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  } catch (e) {
    return "";
  }
};
const lisible = (v) =>
  typeof v === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(v) ? dateCourte(v) : v;
const dateCourte = (iso) => {
  try {
    return new Date(iso).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch (e) {
    return iso;
  }
};

class LightsSimulatorPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._onglet = "fonctionnement";
    this._donnees = null;
    this._lampe = null;
    this._message = null;
    this._erreur = null;
  }

  set hass(hass) {
    const premier = !this._hass;
    this._hass = hass;
    if (premier) this._charger();
  }

  set narrow(v) { this._narrow = v; }
  set panel(v) { this._panel = v; }

  connectedCallback() {
    if (!this._ecoute) {
      this.shadowRoot.addEventListener("click", (e) => this._clic(e));
      this.shadowRoot.addEventListener("change", (e) => this._changement(e));
      this._ecoute = true;
    }
    this._minuterie = setInterval(() => this._charger(true), 20000);
    this._dessiner();
  }

  disconnectedCallback() {
    clearInterval(this._minuterie);
  }

  async _ws(type, extra = {}) {
    return this._hass.callWS({ type: `${DOMAINE}/${type}`, ...extra });
  }

  async _charger(silencieux = false) {
    if (!this._hass) return;
    try {
      this._donnees = await this._ws("etat");
      this._erreur = null;
    } catch (err) {
      this._erreur = err.message || String(err);
    }
    const actif = this.shadowRoot.activeElement;
    if (silencieux && actif && ["INPUT", "SELECT", "TEXTAREA"].includes(actif.tagName)) return;
    this._dessiner();
  }

  _annoncer(texte) {
    this._message = texte;
    this._dessiner();
    clearTimeout(this._minuterieMessage);
    this._minuterieMessage = setTimeout(() => {
      this._message = null;
      this._dessiner();
    }, 4000);
  }

  async _apres_rechargement(texte) {
    this._annoncer(texte);
    await new Promise((r) => setTimeout(r, 2500));
    await this._charger();
  }

  // ------------------------------------------------------------ événements

  async _clic(e) {
    const cible = e.target.closest("[data-action]");
    if (!cible) return;
    const d = cible.dataset;
    try {
      switch (d.action) {
        case "onglet":
          this._onglet = d.valeur;
          this._dessiner();
          break;
        case "mode":
          this._donnees = await this._ws("mode", { mode: d.valeur });
          this._dessiner();
          break;
        case "choix":
          await this._enregistrer(d.section, d.cle, d.valeur);
          break;
        case "bascule":
          await this._enregistrer(d.section, d.cle, !this._valeur(d.section, d.cle));
          break;
        case "jour": {
          const jours = new Set(this._valeur(d.section, "jours") || []);
          const j = Number(d.valeur);
          jours.has(j) ? jours.delete(j) : jours.add(j);
          await this._enregistrer(d.section, "jours", [...jours].sort());
          break;
        }
        case "liste": {
          const liste = new Set(this._valeur(d.section, d.cle) || []);
          liste.has(d.valeur) ? liste.delete(d.valeur) : liste.add(d.valeur);
          await this._enregistrer(d.section, d.cle, [...liste]);
          break;
        }
        case "lampe-ouvrir": {
          const existante = this._donnees.reglages.lampes.find((l) => l.id === d.valeur);
          this._lampe = existante
            ? JSON.parse(JSON.stringify(existante))
            : { entity_id: "", nom: "", utilisee: true, poids: 3, capteur: null, seuil: 50, si_eclairee: "autre",
                action_eclairee: null, eteindre_si_eclairee: false, action_allumage: null, action_extinction: null, garder_retour: false };
          this._dessiner();
          break;
        }
        case "lampe-fermer":
          this._lampe = null;
          this._dessiner();
          break;
        case "lampe-champ":
          this._lampe[d.cle] = d.valeur === "true" ? true : d.valeur === "false" ? false : d.valeur;
          this._dessiner();
          break;
        case "lampe-enregistrer": {
          if (!this._lampe.entity_id || !this._lampe.nom) {
            this._annoncer("Choisissez une lumière et donnez-lui un nom.");
            return;
          }
          const res = await this._ws("lampe_enregistrer", { lampe: this._lampe });
          this._lampe = null;
          if (res.recharge) await this._apres_rechargement("Lampe enregistrée, rechargement…");
          else await this._charger();
          break;
        }
        case "lampe-supprimer":
          if (!confirm(`Retirer « ${this._lampe.nom} » du simulateur ?`)) return;
          await this._ws("lampe_supprimer", { lampe_id: this._lampe.id });
          this._lampe = null;
          await this._apres_rechargement("Lampe retirée, rechargement…");
          break;
        case "lampe-tester":
          this._donnees = await this._ws("lampe_tester", { lampe_id: d.valeur });
          this._annoncer("Lampe allumée pour 2 minutes.");
          break;
        case "sauvegarde-creer": {
          const nom = this.shadowRoot.getElementById("nom-sauvegarde")?.value || "";
          this._donnees = await this._ws("sauvegarde_creer", { nom });
          this._annoncer("Sauvegarde créée.");
          break;
        }
        case "sauvegarde-restaurer":
          if (!confirm("Remplacer la configuration actuelle par cette sauvegarde ? Une copie de la configuration actuelle sera faite avant.")) return;
          await this._ws("sauvegarde_restaurer", { sauvegarde_id: d.valeur });
          await this._apres_rechargement("Sauvegarde restaurée, rechargement…");
          break;
        case "sauvegarde-supprimer":
          if (!confirm("Supprimer cette sauvegarde ?")) return;
          this._donnees = await this._ws("sauvegarde_supprimer", { sauvegarde_id: d.valeur });
          this._dessiner();
          break;
        case "telecharger": {
          const donnees = await this._ws("exporter", d.valeur ? { sauvegarde_id: d.valeur } : {});
          const blob = new Blob([JSON.stringify(donnees, null, 2)], { type: "application/json" });
          const lien = document.createElement("a");
          lien.href = URL.createObjectURL(blob);
          lien.download = `lights_simulator_${(donnees.date || "").slice(0, 10)}.json`;
          lien.click();
          URL.revokeObjectURL(lien.href);
          break;
        }
        case "importer":
          this.shadowRoot.getElementById("fichier")?.click();
          break;
      }
    } catch (err) {
      this._annoncer(`Erreur : ${err.message || err}`);
    }
  }

  async _changement(e) {
    const el = e.target;
    const d = el.dataset;
    try {
      if (el.id === "fichier") {
        const fichier = el.files?.[0];
        if (!fichier) return;
        const donnees = JSON.parse(await fichier.text());
        el.value = "";
        if (!confirm(`Importer « ${fichier.name} » ? Une copie de la configuration actuelle sera faite avant.`)) return;
        await this._ws("importer", { donnees });
        await this._apres_rechargement("Configuration importée, rechargement…");
        return;
      }
      if (d.lampe) {
        let v = el.type === "checkbox" ? el.checked : el.value;
        if (v === "") v = null;
        else if (el.type === "number") v = Number(v);
        this._lampe[d.lampe] = v;
        this._dessiner();
        return;
      }
      if (d.section) {
        let v = el.value;
        if (v === "") v = null;
        else if (el.type === "number") v = Number(v);
        else if (el.type === "time") v = v.slice(0, 5);
        await this._enregistrer(d.section, d.cle, v);
      }
    } catch (err) {
      this._annoncer(`Erreur : ${err.message || err}`);
    }
  }

  _valeur(section, cle) {
    const r = this._donnees?.reglages || {};
    return section === "general" ? r[cle] : (r[section] || {})[cle];
  }

  async _enregistrer(section, cle, valeur) {
    this._donnees = await this._ws("reglages", { section, valeurs: { [cle]: valeur } });
    this._dessiner();
  }

  // ------------------------------------------------------------ éléments

  _entites(filtre) {
    return Object.values(this._hass?.states || {})
      .filter(filtre)
      .map((e) => [e.entity_id, e.attributes.friendly_name || e.entity_id])
      .sort((a, b) => a[1].localeCompare(b[1]));
  }

  _liste(attrs, options, valeur, vide = "Aucun") {
    const opts = [`<option value="">${esc(vide)}</option>`]
      .concat(options.map(([v, l]) => `<option value="${esc(v)}" ${v === valeur ? "selected" : ""}>${esc(l)}</option>`));
    if (valeur && !options.some(([v]) => v === valeur)) opts.push(`<option value="${esc(valeur)}" selected>${esc(valeur)} (introuvable)</option>`);
    return `<select ${attrs}>${opts.join("")}</select>`;
  }

  _segment(section, cle, choix, valeur, label) {
    return `<div class="seg" role="group" aria-label="${esc(label)}">${choix
      .map(([v, l]) => `<button type="button" class="${v === valeur ? "on" : ""}" aria-pressed="${v === valeur}" data-action="choix" data-section="${section}" data-cle="${cle}" data-valeur="${v}">${esc(l)}</button>`)
      .join("")}</div>`;
  }

  _jours(section, jours) {
    return `<div class="chips" role="group" aria-label="Jours">${JOURS.map((j, i) => {
      const on = (jours || []).includes(i);
      return `<button type="button" class="chip ${on ? "on" : ""}" aria-pressed="${on}" data-action="jour" data-section="${section}" data-valeur="${i}">${j}</button>`;
    }).join("")}</div>`;
  }

  _champ(label, section, cle, type, valeur, unite = "") {
    const id = `${section}-${cle}`;
    return `<div class="row"><label for="${id}">${esc(label)}</label><span><input id="${id}" type="${type}" value="${esc(valeur ?? "")}" data-section="${section}" data-cle="${cle}">${unite ? ` ${esc(unite)}` : ""}</span></div>`;
  }

  _interrupteur(label, section, cle, valeur) {
    return `<div class="row"><span>${esc(label)}</span><button type="button" class="sw ${valeur ? "on" : ""}" role="switch" aria-checked="${!!valeur}" aria-label="${esc(label)}" data-action="bascule" data-section="${section}" data-cle="${cle}"><span></span></button></div>`;
  }

  _info(texte) {
    return `<div class="info">${esc(texte)}</div>`;
  }

  // ------------------------------------------------------------ onglets

  _fonctionnement() {
    const i = this._donnees.instantane;
    const pill = i.mode === "arret" ? "gris" : i.actif ? "orange" : "bleu";
    const lampes = i.lampes_allumees.length
      ? i.lampes_allumees.map((l) => `<div class="row"><span>${esc(l.nom)}</span><span class="k">s'éteint dans ${l.reste} min</span></div>`).join("")
      : `<p class="k">Aucune pour l'instant.</p>`;
    const journal = i.journal.length
      ? i.journal.slice(0, 12).map((j) => `<div class="row debut"><span class="k heure">${heure(j.t)}</span><span>${esc(j.texte)}</span></div>`).join("")
      : `<p class="k">Rien pour l'instant.</p>`;
    const echecs = Object.keys(i.echecs || {});
    return `
      <section class="card">
        <h2>État</h2>
        <div class="etat"><span class="pill ${pill}">${esc(i.etat)}</span></div>
        <div class="seg" role="group" aria-label="Mode">${MODES.map(([v, l]) => `<button type="button" class="${v === i.mode ? "on" : ""}" aria-pressed="${v === i.mode}" data-action="mode" data-valeur="${v}">${l}</button>`).join("")}</div>
        <div class="lignes">
          <div class="row"><span class="k">Maison vide</span><span>${i.vide ? "Oui" : "Non"}</span></div>
          <div class="row"><span class="k">Dans une plage</span><span>${i.plage ? "Oui" : "Non"}</span></div>
          <div class="row"><span class="k">Démarrage</span><span>${esc(i.demarrage)}</span></div>
          <div class="row"><span class="k">Fin tirée pour ce soir</span><span>${esc(i.fin_ce_soir || "—")}</span></div>
          <div class="row"><span class="k">Prochaine action</span><span>${esc(i.prochain || "—")}</span></div>
          ${echecs.length ? `<div class="row"><span class="k">Lampes écartées</span><span>${esc(echecs.join(", "))}</span></div>` : ""}
        </div>
      </section>
      <section class="card">
        <h2>Soleil</h2>
        <div class="soleil">
          ${[["lever", "Lever", i.lever], ["coucher", "Coucher", i.coucher]].map(([c, l, v]) => {
            const [jour, demain] = String(v || "—").split(" · ");
            return `<div class="astre ${c}"><div class="k">${l}</div><div class="gros">${esc(jour)}</div>${demain ? `<div class="k">${esc(demain)}</div>` : ""}</div>`;
          }).join("")}
        </div>
      </section>
      <section class="card"><h2>Lampes allumées par le simulateur</h2>${lampes}</section>
      <section class="card"><h2>Journal</h2>${journal}</section>`;
  }

  _capteursLux() {
    return this._entites((e) => e.entity_id.startsWith("sensor.") && e.attributes.device_class === "illuminance");
  }

  _plages() {
    const r = this._donnees.reglages;
    const s = r.soir, m = r.matin;
    const lux = this._capteursLux();
    const i = this._donnees.instantane;
    let debut = "";
    if (s.debut_mode === "soleil") {
      debut = this._champ("Minutes après le coucher (±)", "soir", "decalage_coucher", "number", s.decalage_coucher) +
        this._info(`Coucher aujourd'hui : ${i.coucher}`);
    } else if (s.debut_mode === "fixe") {
      debut = this._champ("Heure de début", "soir", "heure_debut", "time", s.heure_debut);
    } else {
      debut = `<div class="row"><label for="soir-lux">Capteur de luminosité extérieur</label>${this._liste('id="soir-lux" data-section="soir" data-cle="lux_capteur"', lux, s.lux_capteur, "À choisir")}</div>` +
        this._champ("Démarrer quand elle passe sous", "soir", "lux_seuil", "number", s.lux_seuil, "lx") +
        this._champ("Pendant au moins", "soir", "lux_duree", "number", s.lux_duree, "min") +
        this._champ("Pas avant", "soir", "lux_pas_avant", "time", s.lux_pas_avant) +
        this._info(lux.length ? "Si le capteur ne répond pas : repli sur le soleil." : "Aucun capteur de luminosité trouvé : repli sur le soleil.");
    }
    let fin = "";
    if (m.fin_mode === "soleil") {
      fin = this._champ("Minutes après le lever (±)", "matin", "decalage_lever", "number", m.decalage_lever) +
        this._info(`Lever aujourd'hui : ${i.lever}`);
    } else if (m.fin_mode === "fixe") {
      fin = this._champ("Heure de fin", "matin", "heure_fin", "time", m.heure_fin);
    } else {
      fin = `<div class="row"><label for="matin-lux">Capteur de luminosité extérieur</label>${this._liste('id="matin-lux" data-section="matin" data-cle="lux_capteur"', lux, m.lux_capteur, "À choisir")}</div>` +
        this._champ("Arrêter quand elle dépasse", "matin", "lux_seuil", "number", m.lux_seuil, "lx") +
        this._champ("Au plus tard", "matin", "lux_au_plus_tard", "time", m.lux_au_plus_tard) +
        this._info(lux.length ? "Si le capteur ne répond pas : repli sur le soleil." : "Aucun capteur de luminosité trouvé : repli sur le soleil.");
    }
    return `
      <section class="card">
        <h2>Plage du soir</h2>
        <p class="sous">Démarre selon le soleil, une heure ou la luminosité ; se termine à une heure tirée au hasard.</p>
        <h3>Début</h3>${this._segment("soir", "debut_mode", BORNES, s.debut_mode, "Début du soir")}${debut}
        <h3>Fin</h3>
        ${this._champ("Heure moyenne", "soir", "fin", "time", s.fin)}
        ${this._champ("Variation (± min)", "soir", "variation", "number", s.variation)}
        <div class="row"><span>Fin tirée pour ce soir</span><strong>${esc(i.fin_ce_soir || "—")}</strong></div>
        <h3>Jours</h3>${this._jours("soir", s.jours)}
      </section>
      <section class="card">
        <h2>Plage du matin</h2>
        <p class="sous">Commence à une heure fixe ; se termine selon le soleil, une heure ou la luminosité.</p>
        ${this._interrupteur("Activer le matin", "matin", "actif", m.actif)}
        ${m.actif ? `
          <h3>Début</h3>${this._champ("Heure de début", "matin", "debut", "time", m.debut)}
          <h3>Fin</h3>${this._segment("matin", "fin_mode", BORNES, m.fin_mode, "Fin du matin")}${fin}
          <h3>Jours</h3>${this._jours("matin", m.jours)}` : ""}
      </section>`;
  }

  _lampes() {
    const lignes = this._donnees.reglages.lampes.map((l) => {
      const etat = this._hass.states[l.capteur];
      const lux = etat && !isNaN(parseFloat(etat.state)) ? `${Math.round(parseFloat(etat.state))} lx` : "";
      const action = l.capteur ? (SI_ECLAIREE.find((s) => s[0] === l.si_eclairee) || SI_ECLAIREE[0])[1] : "—";
      return `<tr>
        <td><strong>${esc(l.nom)}</strong><span class="ent">${esc(l.entity_id)}</span></td>
        <td><span class="tag ${l.utilisee ? "oui" : "non"}">${l.utilisee ? "Oui" : "Non"}</span></td>
        <td>${esc(l.poids)}</td>
        <td>${l.capteur ? esc(l.capteur) : "Aucun"}${lux ? `<span class="ent">actuellement ${esc(lux)}</span>` : ""}</td>
        <td class="nowrap">${l.capteur ? `${esc(l.seuil)} lx` : "—"}</td>
        <td>${esc(action)}</td>
        <td class="nowrap">${l.garder_retour ? "Garder allumée" : "—"}</td>
        <td class="actions"><button type="button" class="btn" data-action="lampe-tester" data-valeur="${esc(l.id)}">Tester</button><button type="button" class="btn" data-action="lampe-ouvrir" data-valeur="${esc(l.id)}">Modifier</button></td>
      </tr>`;
    }).join("");
    return `
      <div class="entete-lampes">
        <p>Chaque lampe a ses propres réglages : poids, capteur de luminosité facultatif et ce qu'il faut faire quand la pièce est déjà éclairée.</p>
        <button type="button" class="btn primaire" data-action="lampe-ouvrir" data-valeur="">Ajouter une lampe</button>
      </div>
      <section class="card large"><div class="defile"><table>
        <thead><tr><th>Lampe</th><th>Utilisée</th><th>Poids</th><th>Capteur de luminosité</th><th>Seuil</th><th>Si la pièce est déjà éclairée</th><th>Retour de nuit</th><th><span class="masque">Actions</span></th></tr></thead>
        <tbody>${lignes || `<tr><td colspan="8" class="k">Aucune lampe.</td></tr>`}</tbody>
      </table></div></section>`;
  }

  _dialogLampe() {
    const l = this._lampe;
    const lumieres = this._entites((e) => e.entity_id.startsWith("light."));
    const actions = this._entites((e) => /^(script|scene|automation)\./.test(e.entity_id));
    const etat = this._hass.states[l.capteur];
    const lux = etat && !isNaN(parseFloat(etat.state)) ? parseFloat(etat.state) : null;
    const bornes = l.poids >= 4 ? "moitié haute de la durée d'allumage" : l.poids <= 2 ? "moitié basse de la durée d'allumage" : "toute la durée d'allumage";
    const choix = SI_ECLAIREE.map(([v, titre, detail]) => `
      <button type="button" class="opt ${l.si_eclairee === v ? "on" : ""}" aria-pressed="${l.si_eclairee === v}" data-action="lampe-champ" data-cle="si_eclairee" data-valeur="${v}">
        <span class="dot"></span><span><strong>${esc(titre)}</strong><span class="ent">${esc(detail)}</span></span>
      </button>`).join("");
    const caseACocher = (cle, label) => `<label class="row"><span>${esc(label)}</span><input type="checkbox" data-lampe="${cle}" ${l[cle] ? "checked" : ""}></label>`;
    return `
      <div class="voile">
        <div class="dialogue" role="dialog" aria-modal="true" aria-label="${l.id ? "Modifier la lampe" : "Ajouter une lampe"}">
          <div class="dtete"><h2>${l.id ? "Modifier la lampe" : "Ajouter une lampe"}</h2><button type="button" class="fermer" aria-label="Fermer" data-action="lampe-fermer">✕</button></div>
          <div class="dsec">
            <h3>Lampe</h3>
            <label class="champ">Entité lumière${this._liste('data-lampe="entity_id"', lumieres, l.entity_id, "À choisir")}</label>
            <label class="champ">Nom affiché (badge et journal)<input type="text" data-lampe="nom" value="${esc(l.nom)}"></label>
            ${caseACocher("utilisee", "Utilisée par le simulateur")}
            <div class="row"><label for="poids">Poids (0 = jamais, 5 = souvent et longtemps)</label><input id="poids" type="number" min="0" max="5" data-lampe="poids" value="${esc(l.poids)}"></div>
            <div class="info">Poids ${esc(l.poids)} : ${bornes}.</div>
          </div>
          <div class="dsec gris">
            <h3>Luminosité de la pièce (facultatif)</h3>
            <label class="champ">Capteur de luminosité${this._liste('data-lampe="capteur"', this._capteursLux(), l.capteur, "Aucun")}</label>
            ${l.capteur ? `
              <div class="row"><label for="seuil">Pièce considérée comme éclairée à partir de</label><span><input id="seuil" type="number" data-lampe="seuil" value="${esc(l.seuil)}"> lx</span></div>
              ${lux !== null ? `<div class="row"><span>En ce moment</span><strong>${lux >= l.seuil ? "Éclairée" : "Sombre"} (${Math.round(lux)} lx)</strong></div>` : ""}
              <p><strong>Si la pièce est déjà éclairée au moment d'allumer :</strong></p>${choix}
              ${l.si_eclairee === "action" ? `<label class="champ">Action à lancer (script, scène ou automatisation)${this._liste('data-lampe="action_eclairee"', actions, l.action_eclairee, "À choisir")}</label>` : ""}
              ${caseACocher("eteindre_si_eclairee", "Éteindre plus tôt si la pièce devient éclairée pendant l'allumage")}` : `<div class="info">Sans capteur, la lampe s'allume toujours quand elle est tirée.</div>`}
          </div>
          <div class="dsec">
            <h3>Actions supplémentaires (facultatif)</h3>
            <label class="champ">Quand le simulateur allume cette lampe${this._liste('data-lampe="action_allumage"', actions, l.action_allumage, "Aucune")}</label>
            <label class="champ">Quand le simulateur l'éteint${this._liste('data-lampe="action_extinction"', actions, l.action_extinction, "Aucune")}</label>
            ${caseACocher("garder_retour", "Garder allumée au retour de nuit")}
          </div>
          <div class="dpied">
            ${l.id ? `<button type="button" class="btn danger" data-action="lampe-supprimer">Retirer la lampe</button>` : "<span></span>"}
            <span><button type="button" class="btn" data-action="lampe-fermer">Annuler</button> <button type="button" class="btn primaire" data-action="lampe-enregistrer">Enregistrer</button></span>
          </div>
        </div>
      </div>`;
  }

  _rythme() {
    const r = this._donnees.reglages;
    const ry = r.rythme;
    const alarmes = this._entites((e) => e.entity_id.startsWith("alarm_control_panel."));
    const personnes = this._entites((e) => e.entity_id.startsWith("person."));
    const avecAlarme = r.declencheur !== "personnes";
    const avecPersonnes = r.declencheur !== "alarme";
    return `
      <section class="card">
        <h2>Déclenchement (mode Auto)</h2>
        <p class="sous">La simulation tourne dans une plage quand la maison est vide.</p>
        <h3>La maison est vide quand…</h3>
        ${this._segment("general", "declencheur", DECLENCHEURS, r.declencheur, "Déclenchement")}
        ${avecAlarme ? `
          <div class="row"><label for="alarme">Alarme</label>${this._liste('id="alarme" data-section="general" data-cle="alarme"', alarmes, r.alarme, "À choisir")}</div>
          <div class="k petit">États qui comptent comme « absent »</div>
          <div class="chips">${ETATS_ALARME.map(([v, l]) => {
            const on = (r.etats_absence || []).includes(v);
            return `<button type="button" class="chip ${on ? "on" : ""}" aria-pressed="${on}" data-action="liste" data-section="general" data-cle="etats_absence" data-valeur="${v}">${l}</button>`;
          }).join("")}</div>` : ""}
        ${avecPersonnes ? `
          <div class="k petit">Personnes (toutes absentes = maison vide)</div>
          <div class="chips">${personnes.map(([v, l]) => {
            const on = (r.personnes || []).includes(v);
            return `<button type="button" class="chip ${on ? "on" : ""}" aria-pressed="${on}" data-action="liste" data-section="general" data-cle="personnes" data-valeur="${esc(v)}">${esc(l)}</button>`;
          }).join("") || `<span class="k">Aucune personne dans Home Assistant.</span>`}</div>` : ""}
        ${this._champ("Délai avant de considérer la maison vide", "general", "delai_vide", "number", r.delai_vide, "min")}
        <div class="row"><span class="k">Source momentanément indisponible</span><span>garder l'état précédent</span></div>
        <div class="row"><span class="k">Au retour</span><span>éteindre ses lampes, sauf « garder allumée » la nuit</span></div>
      </section>
      <section class="card">
        <h2>Rythme</h2>
        <p class="sous">Durées tirées au hasard à chaque allumage.</p>
        ${this._champ("Allumage minimum", "rythme", "allumage_min", "number", ry.allumage_min, "min")}
        ${this._champ("Allumage maximum", "rythme", "allumage_max", "number", ry.allumage_max, "min")}
        ${this._champ("Pause entre deux tentatives, minimum", "rythme", "pause_min", "number", ry.pause_min, "min")}
        ${this._champ("Pause entre deux tentatives, maximum", "rythme", "pause_max", "number", ry.pause_max, "min")}
        ${this._champ("Lampes allumées en même temps, maximum", "rythme", "simultanees", "number", ry.simultanees)}
      </section>
      <section class="card">
        <h2>Contrôle des lampes</h2>
        <p class="sous">Une lampe qui ne répond pas est mise de côté.</p>
        ${this._champ("Attendre la confirmation de l'allumage", "rythme", "confirmation_s", "number", ry.confirmation_s, "s")}
        ${this._champ("Écarter une lampe sans réponse pendant", "rythme", "ecart_min", "number", ry.ecart_min, "min")}
        <div class="row"><span class="k">Après un redémarrage de Home Assistant</span><span>reprendre le temps restant</span></div>
      </section>`;
  }

  _entitesOnglet() {
    const lignes = this._donnees.entites
      .map((e) => `<tr><td><code>${esc(e.entity_id)}</code></td><td>${esc(e.nom)}</td><td class="k">${esc(lisible(e.etat))}</td></tr>`)
      .join("");
    return `<section class="card large">
      <h2>Entités créées par Lights Simulator</h2>
      <div class="defile"><table><thead><tr><th>Entité</th><th>Nom</th><th>État</th></tr></thead><tbody>${lignes}</tbody></table></div>
      <p class="k petit">Les réglages (plages, rythme, capteurs, actions) sont gardés dans l'intégration et modifiés depuis ce panneau ; ils ne créent pas d'entités supplémentaires.</p>
    </section>`;
  }

  _sauvegarde() {
    const liste = this._donnees.sauvegardes
      .map((s) => `<tr>
        <td><strong>${esc(s.nom)}</strong><span class="ent">${esc(dateCourte(s.date))} · version ${esc(s.version || "?")} · ${s.lampes} lampe(s)</span></td>
        <td class="actions">
          <button type="button" class="btn" data-action="sauvegarde-restaurer" data-valeur="${esc(s.id)}">Restaurer</button>
          <button type="button" class="btn" data-action="telecharger" data-valeur="${esc(s.id)}">Télécharger</button>
          <button type="button" class="btn danger" data-action="sauvegarde-supprimer" data-valeur="${esc(s.id)}" aria-label="Supprimer ${esc(s.nom)}">Supprimer</button>
        </td></tr>`)
      .join("");
    return `
      <section class="card">
        <h2>Sauvegarder la configuration</h2>
        <p class="sous">Garde une copie de tous les réglages (plages, rythme, lampes, capteurs, actions) dans Home Assistant. Les 10 dernières sont conservées.</p>
        <div class="row"><label for="nom-sauvegarde">Nom (facultatif)</label><input id="nom-sauvegarde" type="text" placeholder="Ex. : réglages d'hiver" class="large"></div>
        <div class="boutons"><button type="button" class="btn primaire" data-action="sauvegarde-creer">Créer une sauvegarde</button></div>
      </section>
      <section class="card">
        <h2>Fichier</h2>
        <p class="sous">Pour garder la configuration hors de Home Assistant ou la copier sur une autre installation.</p>
        <div class="boutons">
          <button type="button" class="btn" data-action="telecharger" data-valeur="">Télécharger la configuration actuelle</button>
          <button type="button" class="btn" data-action="importer">Importer un fichier…</button>
          <input id="fichier" type="file" accept="application/json,.json" hidden>
        </div>
        <p class="k petit">Avant chaque restauration ou import, une sauvegarde « Avant… » de la configuration actuelle est créée automatiquement.</p>
      </section>
      <section class="card large">
        <h2>Sauvegardes enregistrées</h2>
        <div class="defile"><table><tbody>${liste || `<tr><td class="k">Aucune sauvegarde pour l'instant.</td></tr>`}</tbody></table></div>
      </section>`;
  }

  // ------------------------------------------------------------ dessin

  _dessiner() {
    if (!this.shadowRoot) return;
    let contenu;
    if (this._erreur && !this._donnees) contenu = `<section class="card"><h2>Lights Simulator</h2><p>${esc(this._erreur)}</p></section>`;
    else if (!this._donnees) contenu = `<section class="card"><p class="k">Chargement…</p></section>`;
    else contenu = {
      fonctionnement: () => this._fonctionnement(),
      plages: () => this._plages(),
      lampes: () => this._lampes(),
      rythme: () => this._rythme(),
      entites: () => this._entitesOnglet(),
      sauvegarde: () => this._sauvegarde(),
    }[this._onglet]();
    const version = this._donnees?.instantane?.version || "";
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <div class="barre">
        <div class="titre">
          ${this._narrow ? `<button type="button" class="menu" aria-label="Menu" onclick="this.getRootNode().host.dispatchEvent(new Event('hass-toggle-menu',{bubbles:true,composed:true}))">☰</button>` : ""}
          <h1>Lights Simulator</h1><span class="k">${esc(version)}</span>
        </div>
        <nav aria-label="Onglets">${ONGLETS.map(([v, l]) => `<button type="button" class="onglet ${v === this._onglet ? "on" : ""}" aria-current="${v === this._onglet ? "page" : "false"}" data-action="onglet" data-valeur="${v}">${l}</button>`).join("")}</nav>
      </div>
      ${this._message ? `<div class="message" role="status">${esc(this._message)}</div>` : ""}
      <main class="${["lampes", "entites"].includes(this._onglet) ? "pile" : "grille"}">${contenu}</main>
      ${this._lampe ? this._dialogLampe() : ""}`;
  }
}

const STYLE = `
  :host { display: block; min-height: 100vh; background: var(--primary-background-color, #f5f5f5); color: var(--primary-text-color, #212121); font-family: var(--paper-font-body1_-_font-family, Roboto, system-ui, sans-serif); --bleu: var(--primary-color, #0277bd); }
  .barre { background: var(--app-header-background-color, var(--card-background-color, #fff)); color: var(--app-header-text-color, inherit); border-bottom: 1px solid var(--divider-color, #e0e0e0); padding: 12px 16px 0; }
  .titre { display: flex; align-items: baseline; gap: 12px; } h1 { margin: 0; font-size: 22px; font-weight: 500; }
  .menu { border: 0; background: none; font-size: 20px; color: inherit; min-width: 44px; min-height: 44px; cursor: pointer; }
  nav { display: flex; flex-wrap: wrap; gap: 2px; margin-top: 8px; }
  .onglet { border: 0; background: none; padding: 12px 14px; font-family: inherit; font-size: 14px; font-weight: 500; color: var(--secondary-text-color, #616161); border-bottom: 2px solid transparent; cursor: pointer; min-height: 44px; }
  .onglet.on { color: var(--bleu); border-bottom-color: var(--bleu); }
  main { max-width: 1180px; margin: 0 auto; padding: 20px 16px; box-sizing: border-box; }
  main.grille { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 380px), 1fr)); gap: 20px; align-items: start; }
  main.pile { display: flex; flex-direction: column; gap: 16px; }
  .card { background: var(--card-background-color, #fff); border-radius: var(--ha-card-border-radius, 12px); border: 1px solid var(--divider-color, #e0e0e0); padding: 20px; }
  .card.large { padding: 12px; }
  h2 { margin: 0 0 8px; font-size: 18px; font-weight: 500; } h3 { margin: 16px 0 4px; font-size: 14px; font-weight: 500; }
  .sous, .k { color: var(--secondary-text-color, #616161); } .sous { margin: 0 0 8px; font-size: 13px; } .petit { font-size: 13px; margin: 8px 0 4px; }
  .row { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 8px 0; border-top: 1px solid var(--divider-color, #eee); font-size: 14px; min-height: 44px; box-sizing: border-box; }
  .row.debut { justify-content: flex-start; } .heure { min-width: 44px; }
  .info { font-size: 13px; color: var(--secondary-text-color, #616161); padding: 4px 0 8px; }
  input[type=number], input[type=time], input[type=text], select { border: 1px solid var(--divider-color, #bdbdbd); border-radius: 6px; padding: 8px 10px; font: inherit; font-size: 14px; background: var(--card-background-color, #fff); color: inherit; min-height: 40px; box-sizing: border-box; }
  input[type=number] { width: 100px; text-align: right; } input[type=time] { width: 130px; } select { max-width: 280px; } input.large { width: 260px; }
  .seg { display: flex; border: 1px solid var(--divider-color, #bdbdbd); border-radius: 8px; overflow: hidden; margin: 8px 0; }
  .seg button { flex: 1; border: 0; background: transparent; padding: 8px; font-family: inherit; font-size: 13px; font-weight: 500; color: inherit; cursor: pointer; min-height: 44px; }
  .seg button.on { background: var(--bleu); color: #fff; }
  .chips { display: flex; flex-wrap: wrap; gap: 8px; padding: 8px 0; }
  .chip { min-width: 52px; min-height: 44px; padding: 0 12px; border-radius: 22px; border: 1px solid var(--divider-color, #9e9e9e); background: transparent; color: inherit; font-family: inherit; font-size: 14px; font-weight: 500; cursor: pointer; }
  .chip.on { background: var(--bleu); border-color: var(--bleu); color: #fff; }
  .sw { width: 44px; height: 24px; border-radius: 12px; border: 0; background: #9e9e9e; position: relative; cursor: pointer; }
  .sw span { position: absolute; top: 3px; left: 3px; width: 18px; height: 18px; border-radius: 9px; background: #fff; transition: left .15s; }
  .sw.on { background: var(--bleu); } .sw.on span { left: 23px; }
  .etat { margin-bottom: 8px; } .pill { display: inline-block; padding: 6px 14px; border-radius: 16px; font-weight: 500; font-size: 14px; }
  .pill.gris { background: #eeeeee; color: #424242; } .pill.orange { background: #ffe0b2; color: #6d3a00; } .pill.bleu { background: #e1f5fe; color: #01579b; }
  .soleil { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; } .astre { border-radius: 10px; padding: 14px; }
  .lever { background: #fff8e1; color: #3e2a00; } .coucher { background: #ede7f6; color: #2a1a5e; } .astre .k { color: inherit; opacity: .85; font-size: 13px; } .gros { font-size: 22px; font-weight: 500; }
  .defile { overflow-x: auto; } table { border-collapse: collapse; width: 100%; font-size: 14px; }
  th { text-align: left; font-weight: 500; color: var(--secondary-text-color, #616161); font-size: 13px; padding: 10px 12px; border-bottom: 1px solid var(--divider-color, #e0e0e0); white-space: nowrap; }
  td { padding: 10px 12px; border-bottom: 1px solid var(--divider-color, #eee); vertical-align: middle; } td.actions { white-space: nowrap; text-align: right; }
  .ent { display: block; font-size: 12px; color: var(--secondary-text-color, #616161); font-weight: 400; }
  .tag { display: inline-block; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; } .tag.oui { background: #e8f5e9; color: #1b5e20; } .tag.non { background: #eeeeee; color: #424242; }
  .btn { min-height: 40px; padding: 0 14px; border-radius: 8px; border: 1px solid var(--divider-color, #bdbdbd); background: transparent; color: var(--bleu); font-family: inherit; font-size: 14px; font-weight: 500; cursor: pointer; margin: 2px; }
  .btn.primaire { background: var(--bleu); border-color: var(--bleu); color: #fff; } .btn.danger { color: var(--error-color, #b71c1c); border-color: transparent; }
  .boutons { display: flex; flex-wrap: wrap; gap: 8px; padding-top: 8px; }
  .entete-lampes { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px; } .entete-lampes p { margin: 0; max-width: 720px; font-size: 14px; }
  .masque { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
  code { font-family: ui-monospace, Menlo, monospace; font-size: 13px; }
  td.nowrap { white-space: nowrap; }
  .message { max-width: 1148px; margin: 12px auto 0; padding: 10px 16px; border-radius: 8px; background: #e1f5fe; color: #01579b; font-size: 14px; }
  .voile { position: fixed; inset: 0; background: rgba(0,0,0,.4); display: flex; justify-content: center; align-items: flex-start; overflow-y: auto; padding: 24px 12px; z-index: 10; }
  .dialogue { width: min(640px, 100%); background: var(--card-background-color, #fff); border-radius: 16px; overflow: hidden; }
  .dtete { display: flex; justify-content: space-between; align-items: center; padding: 16px 24px; } .dtete h2 { margin: 0; }
  .fermer { border: 0; background: none; font-size: 18px; min-width: 44px; min-height: 44px; cursor: pointer; color: inherit; }
  .dsec { padding: 12px 24px 16px; border-top: 1px solid var(--divider-color, #eee); } .dsec.gris { background: var(--secondary-background-color, #fafafa); } .dsec h3 { margin-top: 4px; }
  .champ { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--secondary-text-color, #616161); margin-bottom: 12px; } .champ select, .champ input { max-width: none; width: 100%; color: var(--primary-text-color, #212121); }
  .opt { display: flex; gap: 12px; align-items: flex-start; width: 100%; text-align: left; padding: 10px 12px; margin-bottom: 8px; border-radius: 8px; border: 1px solid var(--divider-color, #e0e0e0); background: var(--card-background-color, #fff); color: inherit; font-family: inherit; font-size: 14px; cursor: pointer; }
  .opt.on { border-color: var(--bleu); } .dot { flex: none; width: 18px; height: 18px; border-radius: 9px; border: 2px solid #757575; box-sizing: border-box; margin-top: 1px; } .opt.on .dot { border-color: var(--bleu); background: var(--bleu); }
  .dpied { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; padding: 12px 24px; border-top: 1px solid var(--divider-color, #eee); }
  input[type=checkbox] { width: 20px; height: 20px; }
`;

customElements.define("lights-simulator-panel", LightsSimulatorPanel);
