const $ = (id) => document.getElementById(id);
let state = null;
let selectedObservation = null;
const messages = {
  unknown: 'Inconnu', proposed: 'Proposition IA', recognized_candidate: 'Ressemblance à confirmer',
  learned: 'Appris', analyzing: 'Analyse en cours'
};
function toast(msg, error=false) {
  const el=$('toast'); el.textContent=msg; el.classList.toggle('error',error); el.style.display='block';
  clearTimeout(window.toastTimer); window.toastTimer=setTimeout(()=>el.style.display='none',5500);
}
async function api(path, opts={}) {
  const r=await fetch(path,opts);
  if(!r.ok){let info;try {info=await r.json()}catch{info={}};throw new Error(info.detail||`Erreur HTTP ${r.status}`)}
  return r.json();
}
function elt(tag,cls,text) {const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e}
function button(label, action,cls='secondary') {const b=elt('button',cls+' compact',label);b.type='button';b.addEventListener('click',async()=>{b.disabled=true;try{await action()}catch(e){toast(e.message,true)}finally{b.disabled=false}});return b}
function empty(node,msg){node.replaceChildren(elt('p','empty',msg))}
async function refresh() {
  try{
    const data=await api('/api/state');state=data;
    $('stat-concepts').textContent=data.stats.concepts;
    $('stat-observations').textContent=data.stats.observations;
    $('stat-pending').textContent=data.stats.pending;
    $('stat-facts').textContent=data.stats.verified_facts;
    $('engine-status').textContent=data.ai_enabled?(data.auto_vision?'IA auto : active':(data.remote_reference_matching?'IA multi-angles sur demande':'IA disponible sur demande')):'Mode local : sans IA';
    renderObservations(data.observations);renderConcepts(data.concepts);renderEvents(data.events);
    const curiosity=await api('/api/curiosity');renderCuriosity(curiosity.tasks);
    const report=await api('/api/learning/report');renderLearningReport(report);
    const evolution=await api('/api/evolution');renderEvolution(evolution);
    const continuous=await api('/api/evolution/continuous');renderContinuous(continuous,evolution);
  }catch(e){toast(e.message,true)}
}
function renderObservations(items){
  const host=$('observations');host.replaceChildren();if(!items.length){empty(host,'La mémoire ne contient encore aucune observation.');return}
  for(const o of items){
    const card=elt('div','obs');const img=elt('img');img.src=o.image_url;img.alt='Observation envoyée à Duck';img.loading='lazy';card.append(img);
    const body=elt('div','obs-body');const label=elt('span','status '+o.status,messages[o.status]||o.status);
    const title=elt('strong','',o.candidate_label||'Objet à identifier');const summary=elt('small','',o.notes||`Envoyé par ${o.source}`);
    const actions=elt('div','obs-actions');
    if(o.status!=='learned'){
      actions.append(button('Confirmer',()=>openConfirm(o),'primary'));
      if(state.ai_enabled) actions.append(button('Analyser IA',async()=>{const result=await api(`/api/observations/${o.id}/analyze`,{method:'POST'});toast(result.candidate_label?'Proposition reçue, à vérifier.':'L’IA n’a pas identifié cet objet.');await refresh()}));
    }
    actions.append(button('Effacer',async()=>{if(!confirm('Supprimer définitivement cette image et son exemple associé ?'))return;await api(`/api/observations/${o.id}`,{method:'DELETE'});toast('Observation effacée');await refresh()}));
    body.append(label,title,summary,actions);card.append(body);host.append(card);
  }
}
function renderConcepts(items){
 const host=$('concepts');host.replaceChildren();if(!items.length){empty(host,'Duck ne connaît pas encore d’objet.');return}
 for(const c of items){const item=elt('div','item');const info=elt('div');info.append(elt('h3','',c.label),elt('p','',c.description||c.category));const buttons=elt('div');
 buttons.append(button('Rechercher',async()=>{const r=await api(`/api/concepts/${c.id}/research`,{method:'POST'});toast('Proposition de connaissance enregistrée, à confirmer.');await refresh()}));
 buttons.append(button('×',async()=>{if(!confirm(`Effacer l’objet « ${c.label} » et ses exemples d’apprentissage ?`))return;await api(`/api/concepts/${c.id}`,{method:'DELETE'});toast('Objet effacé');await refresh()}));
 info.style.minWidth='0';buttons.style.display='flex';buttons.style.gap='6px';item.append(info,buttons);host.append(item)}
 // Review researched facts, with their sources and explicit confirmation.
 for(const f of state.facts.filter(x=>x.status==='to_review')) {
  const item=elt('div','item');const info=elt('div');info.style.minWidth='0';info.append(elt('h3','','Connaissance à vérifier'),elt('p','',f.text.slice(0,240)));
  if(f.source_url){const a=elt('a','small-link','Consulter la source');a.href=f.source_url;a.target='_blank';a.rel='noopener noreferrer';info.append(a)}
  const btn=elt('div');btn.style.display='flex';btn.style.gap='6px';
  btn.append(button('Valider',async()=>{await api(`/api/facts/${f.id}/review`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({approve:true})});await refresh()}));
  btn.append(button('Rejeter',async()=>{await api(`/api/facts/${f.id}/review`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({approve:false})});await refresh()}));
  item.append(info,btn);host.append(item)
 }
}
function renderEvents(events){const host=$('events');host.replaceChildren();if(!events.length){empty(host,'Aucune activité');return};for(const ev of events){const item=elt('div','',`${ev.kind} · ${(ev.created_at||'').slice(0,16).replace('T',' ')}`);host.append(item)}}
function renderCuriosity(items){const host=$('curiosity');host.replaceChildren();if(!items.length){empty(host,'Duck n’a pas de découverte en attente.');return};for(const x of items.slice(0,12)){const item=elt('div','item');item.append(elt('p','',x.summary));host.append(item)}}
function renderLearningReport(report){
 const host=$('learning-report');host.replaceChildren();
 const values=[
  ['Exemples visuels confirmés',report.confirmed_examples],
  ['Objets avec plusieurs vues confirmées',report.concepts_with_multiple_views],
  ['Propositions visuelles externes',report.external_vision_proposals],
  ['Faits à vérifier',report.pending_facts],
 ];
 for(const [label,value] of values){
  const row=elt('div','item');row.append(elt('p','',label),elt('h3','',String(value)));host.append(row);
 }
 const note=elt('p','hint',report.note);host.append(note);
}
function openConfirm(o){selectedObservation=o.id;$('label').value=o.candidate_label||'';$('category').value='objet';$('description').value=o.notes||'';$('confirm-hint').textContent=o.candidate_label?`Duck propose « ${o.candidate_label} » (${Math.round(o.confidence*100)} % indicatif). Vérifie avant de confirmer.`:'Donne un nom à l’objet sur cette image.';$('confirm-dialog').showModal()}
$('cancel-dialog').addEventListener('click',()=>$('confirm-dialog').close());
$('confirm-form').addEventListener('submit',async(e)=>{e.preventDefault();try{const data={label:$('label').value,category:$('category').value,description:$('description').value};await api(`/api/observations/${selectedObservation}/confirm`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});$('confirm-dialog').close();toast(`Duck a appris : ${data.label}`);await refresh()}catch(err){toast(err.message,true)}});
$('upload-form').addEventListener('submit',async(e)=>{e.preventDefault();const file=$('image').files[0];if(!file){toast('Choisis une image.',true);return};if(file.size>5*1024*1024){toast('5 Mo maximum',true);return};const button=$('upload-button');button.disabled=true;try{const form=new FormData();form.append('file',file);form.append('source','dashboard');const result=await api('/api/observations',{method:'POST',body:form});toast(result.candidate_label?`Duck pense reconnaître : ${result.candidate_label}. Confirmation nécessaire.`:'Observation enregistrée. Tu peux lui apprendre le nom.');$('image').value='';$('preview').hidden=true;await refresh()}catch(err){toast(err.message,true)}finally{button.disabled=false}});
$('image').addEventListener('change',()=>{const file=$('image').files[0];const el=$('preview');if(!file){el.hidden=true;return};el.src=URL.createObjectURL(file);el.hidden=false});
const zone=$('dropzone');zone.addEventListener('dragover',e=>{e.preventDefault();zone.classList.add('drag')});zone.addEventListener('dragleave',()=>zone.classList.remove('drag'));zone.addEventListener('drop',e=>{e.preventDefault();zone.classList.remove('drag');if(e.dataTransfer.files.length){$('image').files=e.dataTransfer.files;$('image').dispatchEvent(new Event('change'))}});
$('curiosity-cycle').addEventListener('click', async()=>{
 const btn=$('curiosity-cycle');btn.disabled=true;
 try{const r=await api('/api/learning/cycle',{method:'POST'});
 toast(r.status==='already_run_today'?'Recherche déjà effectuée aujourd’hui.':`${r.processed} sujet(s) examiné(s), propositions à vérifier.`);
 await refresh();}catch(e){toast(e.message,true)}finally{btn.disabled=false}
});
$('refresh').addEventListener('click',refresh);refresh();

// V3: admin-only, non-executable diagnostics and review of proposals.
function renderEvolution(data){
 const host=$('evolution-metrics');host.replaceChildren();
 for(const [value,name] of [
   [data.metrics.vision_corrected,'Corrections humaines (30 j)'],
   [data.metrics.unknown_observations,'Observations inconnues'],
   [data.proposals.filter(p=>p.status==='proposed').length,'Propositions à examiner']]){
   const card=elt('div','evo-metric');card.append(elt('strong','',String(value)),elt('span','',name));host.append(card)
 }
 $('diagnosis-status').textContent=data.runs.length
   ?`Dernier diagnostic : ${data.runs[0].created_at.slice(0,16).replace('T',' ')} · ${data.runs[0].findings.length} constat(s)`
   :'Aucun diagnostic réalisé.';
 const list=$('evolution-proposals');list.replaceChildren();
 if(!data.proposals.length){empty(list,'Aucune proposition. Exécute un premier diagnostic.');return}
 for(const p of data.proposals){
   const row=elt('div','evo-proposal');const header=elt('div','evo-proposal-header');
   header.append(elt('h3','',p.title),elt('span','evo-chip '+p.priority,p.priority==='high'?'Priorité haute':p.priority==='medium'?'Priorité moyenne':'Priorité basse'));
   row.append(header,elt('p','',p.explanation));
   const actions=elt('div','evo-proposal-actions');
   const status=elt('span','evo-chip '+p.status,({proposed:'À examiner',approved_for_development:'Étude autorisée',rejected:'Rejetée'})[p.status]||p.status);
   actions.append(status);
   if(p.status==='proposed'){
     actions.append(button('Autoriser l’étude',async()=>{await api(`/api/evolution/proposals/${p.id}/review`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({approve:true})});toast('Étude autorisée : aucun code modifié.');await refresh()},'primary'));
     actions.append(button('Rejeter',async()=>{await api(`/api/evolution/proposals/${p.id}/review`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({approve:false})});await refresh()}));
   }
   actions.append(button('Télécharger le brief',async()=>{window.location.href=`/api/evolution/proposals/${p.id}/brief`;}));
   row.append(actions);list.append(row);
 }
}
$('run-diagnosis').addEventListener('click',async()=>{
 const b=$('run-diagnosis');b.disabled=true;
 try{
   const r=await api('/api/evolution/diagnose',{method:'POST'});
   toast(r.status==='already_run_today'?'Diagnostic déjà effectué aujourd’hui.':`${r.proposals_created} proposition(s) créée(s).`);
   await refresh();
 }catch(e){toast(e.message,true)}finally{b.disabled=false}
});


// V3.3: evidence snapshots and human-reviewed release dossiers, no code deployment.
function renderContinuous(data, evolution){
 const cycles=data.cycles, latest=cycles[0], metrics=$('continuous-metrics');metrics.replaceChildren();
 for(const [value,name] of [
   [cycles.length,'Cycles enregistrés'],
   [latest?latest.benchmark.unique_heldout_samples:'—','Vues hors référence'],
   [latest&&latest.benchmark.accuracy!==null?`${Math.round(latest.benchmark.accuracy*100)} %`:'—','Rappels corrects / toutes vues'],
   [latest?latest.benchmark.wrong:'—','Erreurs visuelles mesurées']]){
   const el=elt('div','evo-metric');el.append(elt('strong','',String(value)),elt('span','',name));metrics.append(el);
 }
 $('continuous-status').textContent=latest
   ?`Dernier cycle : ${latest.day_key} · révision ${latest.code_revision} · ${latest.trend.note}`
   :'Aucun cycle réalisé.';
 const list=$('continuous-cycles');list.replaceChildren();
 if(!cycles.length){empty(list,'Lance un cycle pour établir la première référence.')}
 else for(const c of cycles.slice(0,8)){
   const el=elt('div','evo-proposal');
   const t=elt('h3','',`${c.day_key} — ${c.code_revision}`);
   const b=c.benchmark;
   el.append(t,elt('p','',`${b.unique_heldout_samples} vue(s) évaluée(s) · ${b.correct} correcte(s) · ${b.wrong} erreur(s) · ${b.abstained} abstention(s).`),
        elt('p','hint',c.trend.note));list.append(el)
 }
 const rel=$('continuous-releases');rel.replaceChildren();
 if(!data.release_assessments.length){empty(rel,'Aucun dossier pour le moment.')}
 else for(const a of data.release_assessments){
   const el=elt('div','evo-proposal');el.append(elt('h3','',`${a.base_revision} → ${a.candidate_revision}`),
     elt('p','',a.verdict==='eligible_for_human_review'?'Critères déclarés satisfaits : revue humaine requise.':`Preuves insuffisantes : ${a.reasons.join(' ; ')}`),
     elt('p','hint',`État : ${a.status} · aucun déploiement automatique`));
   if(a.status==='pending_review'){
     const actions=elt('div','evo-proposal-actions');
     if(a.verdict==='eligible_for_human_review')actions.append(button('Valider pour préparation manuelle',async()=>{
       if(!confirm('Confirmer une validation administrative sans installation ni fusion du code ?'))return;
       await api(`/api/evolution/releases/${a.id}/review`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({approve:true})});await refresh();
     },'primary'));
     actions.append(button('Rejeter le dossier',async()=>{await api(`/api/evolution/releases/${a.id}/review`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({approve:false})});await refresh()}));el.append(actions);
   }
   rel.append(el);
 }
 // Populate strictly from reviewed proposals and actual historical cycles.
 const psel=$('release-proposal'),bsel=$('release-baseline'),csel=$('release-candidate');
 const fill=(el,items)=>{const val=el.value;el.replaceChildren();for(const [value,label] of items){const o=elt('option','',label);o.value=value;el.append(o)}if(items.some(x=>x[0]===val))el.value=val};
 fill(psel,evolution.proposals.filter(p=>p.status==='approved_for_development').map(p=>[p.id,p.title]));
 const options=cycles.map(c=>[c.id,`${c.day_key} · ${c.code_revision}`]);fill(bsel,options);fill(csel,options);
 if(!csel.value&&options.length>1)csel.value=options[1][0];
}
$('run-continuous').addEventListener('click',async()=>{
 const b=$('run-continuous');b.disabled=true;
 try{const r=await api('/api/evolution/continuous/cycle',{method:'POST'});
   toast(r.status==='already_run_today'?'Cycle déjà enregistré aujourd’hui.':'Cycle enregistré, métriques et benchmark conservés.');await refresh();
 }catch(e){toast(e.message,true)}finally{b.disabled=false}
});
$('release-assessment-form').addEventListener('submit',async(e)=>{
 e.preventDefault();const b=e.submitter;b.disabled=true;
 try{
  const payload={proposal_id:$('release-proposal').value,baseline_cycle_id:$('release-baseline').value,
   candidate_cycle_id:$('release-candidate').value,
   tests_total:Number($('release-tests-total').value),tests_passed:Number($('release-tests-passed').value),
   ci_report_sha256:$('release-ci-sha').value,
   security_review_attested:$('release-security').checked,
   rollback_prepared_attested:$('release-rollback').checked};
  const r=await api('/api/evolution/releases/assess',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  toast(r.verdict==='eligible_for_human_review'?'Dossier prêt pour revue humaine.':'Dossier enregistré : éléments insuffisants.');await refresh();
 }catch(err){toast(err.message,true)}finally{b.disabled=false}
});
