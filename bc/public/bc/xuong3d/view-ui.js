// Viewport controls deliberately initialize independently of WebGL.
export function createViewportUI(doc=document,win=window){
  const $=id=>doc.getElementById(id),shell=$('factory-shell'),card=$('selection-card');
  const panelsButton=$('panels-toggle'),screenButton=$('fullscreen-toggle');
  const motion=$('motion-toggle'),motionHome=motion.parentElement,motionNext=motion.nextSibling;
  const state={expanded:false,mode:null,panelsHidden:false,busy:false,before:null};
  const mobile=()=>win.matchMedia('(max-width: 760px)').matches;
  const visible=()=>!state.panelsHidden&&!card.hidden&&!doc.body.classList.contains('list-hidden');
  function resize(){win.requestAnimationFrame(()=>win.dispatchEvent(new Event('resize')));win.setTimeout(()=>win.dispatchEvent(new Event('resize')),240);}
  function announce(text){$('viewport-status').textContent=text;}
  function sync(){
    shell.classList.toggle('panels-hidden',state.panelsHidden);
    shell.classList.toggle('viewport-expanded',state.expanded);
    doc.body.classList.toggle('viewport-expanded',state.expanded);
    panelsButton.querySelector('.action-label').textContent=visible()?'Ẩn bảng':'Hiện bảng';
    panelsButton.setAttribute('aria-label',visible()?'Ẩn các bảng để xem 3D':'Hiện lại các bảng');
    panelsButton.setAttribute('aria-expanded',String(visible()));
    screenButton.querySelector('.action-label').textContent=state.expanded?'Thu gọn':'Toàn màn hình';
    screenButton.setAttribute('aria-label',state.expanded?'Thoát toàn màn hình 3D':'Mở toàn màn hình 3D');
    screenButton.setAttribute('aria-pressed',String(state.expanded));
    screenButton.disabled=state.busy;
    screenButton.title=state.expanded?'Thu gọn vùng 3D (Esc)':'Mở rộng vùng 3D';
  }
  function showPanels(){state.panelsHidden=false;card.hidden=false;doc.body.classList.remove('list-hidden');sync();resize();}
  function hidePanels(){state.panelsHidden=true;doc.body.classList.remove('list-open');sync();resize();panelsButton.focus({preventScroll:true});}
  function capture(){return {panelsHidden:state.panelsHidden,cardHidden:card.hidden,listHidden:doc.body.classList.contains('list-hidden'),listOpen:doc.body.classList.contains('list-open')};}
  function prepareExpanded(){if(state.expanded)return;state.before=capture();state.expanded=true;state.mode='fallback';hidePanels();$('view-controls').appendChild(motion);const dialog=$('help-dialog');if(dialog?.open)dialog.close();sync();resize();}
  function finishExpanded(){if(!state.expanded)return;const before=state.before;state.expanded=false;state.mode=null;state.before=null;state.busy=false;if(before){state.panelsHidden=before.panelsHidden;card.hidden=before.cardHidden;doc.body.classList.toggle('list-hidden',before.listHidden);doc.body.classList.toggle('list-open',before.listOpen);}if(motionNext?.parentElement===motionHome)motionHome.insertBefore(motion,motionNext);else motionHome.appendChild(motion);sync();resize();screenButton.focus({preventScroll:true});announce('Đã trở về góc xem thường.');}
  async function enterExpanded(){if(state.busy||state.expanded)return;prepareExpanded();if(typeof shell.requestFullscreen==='function'&&doc.fullscreenEnabled!==false){state.busy=true;sync();try{await shell.requestFullscreen();state.mode=doc.fullscreenElement===shell?'native':'fallback';}catch{state.mode='fallback';}finally{state.busy=false;sync();resize();}}announce(state.mode==='native'?'Đã mở 3D toàn màn hình. Nhấn Esc hoặc Thu gọn để thoát.':'Đã mở rộng 3D trong trình duyệt. Nhấn Esc hoặc Thu gọn để thoát.');}
  async function exitExpanded(){if(state.busy)return;if(doc.fullscreenElement===shell&&typeof doc.exitFullscreen==='function'){state.busy=true;sync();try{await doc.exitFullscreen();if(doc.fullscreenElement!==shell)finishExpanded();}catch{announce('Hãy nhấn Esc để thoát toàn màn hình.');}finally{state.busy=false;sync();}}else finishExpanded();}
  panelsButton.addEventListener('click',()=>visible()?hidePanels():showPanels());
  screenButton.addEventListener('click',()=>state.expanded?exitExpanded():enterExpanded());
  $('clear-selection').addEventListener('click',()=>{card.hidden=true;sync();panelsButton.focus({preventScroll:true});});
  $('collapse').addEventListener('click',()=>{if(mobile())doc.body.classList.remove('list-open');else doc.body.classList.add('list-hidden');sync();resize();});
  $('open-list').addEventListener('click',()=>{state.panelsHidden=false;if(mobile())doc.body.classList.add('list-open');else doc.body.classList.remove('list-hidden');sync();resize();});
  doc.addEventListener('fullscreenchange',()=>{if(doc.fullscreenElement===shell){prepareExpanded();state.mode='native';sync();resize();}else if(state.expanded&&state.mode==='native')finishExpanded();});
  doc.addEventListener('keydown',e=>{if(e.key!=='Escape'||doc.querySelector('dialog[open]'))return;if(state.expanded){if(state.mode==='fallback')e.preventDefault();exitExpanded();}else if(!visible())showPanels();});
  win.addEventListener('rvhg:selection',sync);
  win.addEventListener('orientationchange',resize);
  if(win.visualViewport)win.visualViewport.addEventListener('resize',resize);
  sync();
  return {state,showPanels,hidePanels,enterExpanded,exitExpanded};
}
if(typeof document!=='undefined'&&document.getElementById('factory-shell'))window.__RVHGViewport=createViewportUI();
