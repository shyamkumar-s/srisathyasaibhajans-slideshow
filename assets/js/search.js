document.addEventListener('DOMContentLoaded', ()=>{
  const q = document.getElementById('q')
  const q_top = document.getElementById('q_top')
  const mode_top = document.getElementById('mode_top')
  const btn_top = document.getElementById('search_top')
  const suggBox = document.createElement('div')
  suggBox.style.position = 'absolute'
  suggBox.style.background = '#fff'
  suggBox.style.border = '1px solid #ccc'
  suggBox.style.zIndex = 9999
  suggBox.style.display = 'none'
  suggBox.style.maxHeight = '240px'
  suggBox.style.overflow = 'auto'
  document.body.appendChild(suggBox)
  const mode = document.getElementById('mode')
  const btn = document.getElementById('search')
  let results = document.getElementById('results')
  const reader = document.getElementById('reader')
  const songTitle = document.getElementById('song-title')
  const songMeta = document.getElementById('song-meta')
  const songLyrics = document.getElementById('song-lyrics')

  async function doSearch(){
    const query = q.value.trim()
    if(!query) return
    results.innerHTML = 'Searching...'
    const resp = await fetch(`/search?q=${encodeURIComponent(query)}&mode=${mode.value}&limit=20`)
    const data = await resp.json()
    results.innerHTML = ''
    if(!data.results || data.results.length===0){ results.innerHTML = '<div>No results</div>'; return }
    data.results.forEach(r=>{
      const el = document.createElement('div')
      el.className = 'result'
      const titleDiv = document.createElement('div')
      titleDiv.style.display = 'flex'
      titleDiv.style.alignItems = 'center'
      titleDiv.style.justifyContent = 'space-between'

      const left = document.createElement('div')
      left.innerHTML = `<strong>${r.title}</strong><div class="meta">${r.deity || ''} ${r.tags? ' · '+r.tags:''} · score:${(r.score||0).toFixed(3)}</div>`
      left.style.cursor = 'pointer'
      left.onclick = ()=> addToTodaysList(r)

      const actions = document.createElement('div')
      actions.style.display = 'flex'
      actions.style.gap = '8px'

      const addBtn = document.createElement('button')
      addBtn.textContent = 'Add'
      addBtn.className = 'folder-btn'
      addBtn.style.padding = '6px 10px'
      addBtn.onclick = (ev)=>{ ev.stopPropagation(); addToTodaysList(r) }

      const delBtn = document.createElement('button')
      delBtn.textContent = 'Delete'
      delBtn.className = 'folder-btn btn-secondary'
      delBtn.style.padding = '6px 10px'
      delBtn.onclick = async (ev)=>{
        ev.stopPropagation()
        if(!confirm('Delete "' + r.title + '"? This cannot be undone.')) return
        try{
          const resp = await fetch('/song/' + r.id, { method: 'DELETE' })
          const data = await resp.json()
          if(resp.ok){
            el.remove()
            alert('Deleted: ' + r.title)
            // optionally refresh preview/matches
            if(typeof previewMatches === 'function') previewMatches()
          } else {
            alert('Error deleting: ' + (data.error || 'unknown'))
          }
        }catch(e){ alert('Delete failed: ' + e.message) }
      }

      actions.appendChild(addBtn)
      actions.appendChild(delBtn)

      titleDiv.appendChild(left)
      titleDiv.appendChild(actions)

      el.appendChild(titleDiv)
      results.appendChild(el)
    })
  }

  let acTimer = null
  let activeInput = null
  async function fetchAndShowSuggestions(inputEl, val){
    const resp = await fetch(`/autocomplete?q=${encodeURIComponent(val)}&limit=8`)
    const data = await resp.json()
    suggBox.innerHTML = ''
    if(!data.suggestions || data.suggestions.length===0){ suggBox.style.display='none'; return }
    data.suggestions.forEach(s=>{
      const el = document.createElement('div')
      el.style.padding = '6px'
      el.style.cursor = 'pointer'
      el.innerHTML = `<strong>${s.title}</strong> <span style="color:#666">${s.deity? '· '+s.deity:''}</span>`
      el.onclick = ()=>{ inputEl.value = s.title; suggBox.style.display='none'; doSearch() }
      suggBox.appendChild(el)
    })
    const rect = inputEl.getBoundingClientRect()
    suggBox.style.left = (rect.left + window.scrollX) + 'px'
    suggBox.style.top = (rect.bottom + window.scrollY) + 'px'
    suggBox.style.minWidth = rect.width + 'px'
    suggBox.style.display = 'block'
  }

  function attachAutocompleteTo(inputEl){
    if(!inputEl) return
    inputEl.addEventListener('input', ()=>{
      const val = inputEl.value.trim()
      if(acTimer) clearTimeout(acTimer)
      if(!val){ suggBox.style.display='none'; return }
      activeInput = inputEl
      acTimer = setTimeout(()=> fetchAndShowSuggestions(inputEl, val), 180)
    })
    inputEl.addEventListener('focus', ()=>{ if(inputEl.value.trim()) fetchAndShowSuggestions(inputEl, inputEl.value.trim()) })
  }
  attachAutocompleteTo(q)
  attachAutocompleteTo(q_top)
  document.addEventListener('click', (e)=>{ if(!suggBox.contains(e.target) && e.target !== q && e.target !== q_top) suggBox.style.display='none' })

  async function loadSong(id){
    const resp = await fetch(`/song/${id}`)
    if(!resp.ok) return
    const s = await resp.json()
    songTitle.textContent = s.title
    songMeta.textContent = `${s.deity || ''}${s.tags? ' · '+s.tags: ''}`
    songLyrics.textContent = s.lyrics || ''
    reader.style.display = 'block'
    window.scrollTo({top: reader.offsetTop, behavior:'smooth'})
  }

  function addToTodaysList(r){
    const textarea = document.getElementById('song-list-input')
    if(textarea){
      const line = r.title + (r.deity? ' · '+r.deity : '')
      if(textarea.value.trim().length > 0 && !textarea.value.endsWith('\n')) textarea.value += '\n'
      textarea.value += line + '\n'
      // update preview if existing function available
      if(typeof previewMatches === 'function') previewMatches()
      alert('Added to today\'s list: ' + r.title)
    } else {
      // fallback: open lyrics
      loadSong(r.id)
    }
  }

  btn.addEventListener('click', doSearch)
  if(btn_top) btn_top.addEventListener('click', doSearch)
  q.addEventListener('keydown', (e)=>{ if(e.key==='Enter') doSearch() })
  if(q_top) q_top.addEventListener('keydown', (e)=>{ if(e.key==='Enter') doSearch() })
  // Bind search controls if present in main page
  const resultsContainer = document.getElementById('search-results')
  if(resultsContainer){
    // override results rendering to the page's container
    results = resultsContainer
    const searchBtnMain = document.getElementById('search')
    const addManual = document.getElementById('add-manual')
    if(searchBtnMain) searchBtnMain.addEventListener('click', doSearch)
    if(addManual) addManual.addEventListener('click', ()=>{ const m = document.getElementById('modal'); m.classList.add('open'); m.setAttribute('aria-hidden','false') })
  }
})

// Add-new modal logic
document.addEventListener('click', (e)=>{
  if(e.target && e.target.matches && e.target.matches('.result-add')){
    const m = document.getElementById('modal'); m.classList.add('open'); m.setAttribute('aria-hidden','false')
  }
})
const modal = document.getElementById('modal')
const saveBtn = document.getElementById('save-new')
const cancelBtn = document.getElementById('cancel-new')
if(cancelBtn) cancelBtn.onclick = ()=> { modal.classList.remove('open'); modal.setAttribute('aria-hidden','true') }
if(saveBtn) saveBtn.onclick = async ()=>{
  const title = document.getElementById('new-title').value.trim()
  const deity = document.getElementById('new-deity').value.trim()
  const tags = document.getElementById('new-tags').value.trim()
  const lyrics = document.getElementById('new-lyrics').value.trim()
  if(!title || !lyrics){ alert('Title and lyrics required'); return }
  const resp = await fetch('/song', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,deity,tags,lyrics})})
  const data = await resp.json()
  if(resp.ok){ modal.classList.remove('open'); modal.setAttribute('aria-hidden','true'); alert('Saved'); /* optionally reload */ }
  else alert('Error: '+(data.error||'unknown'))
}
