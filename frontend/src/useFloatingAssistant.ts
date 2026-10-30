import { onMounted, onUnmounted, type Ref } from 'vue'

/** Keep the ever-present assistant clear of pagination controls, without
 * reserving a large empty column throughout the page. */
export function useFloatingAssistant(button: Ref<HTMLElement | null>) {
  let frame=0, lift=0, previous: HTMLElement|null=null, observer: MutationObserver|undefined
  function position() {
    frame=0
    const element=button.value
    if(!element || !element.getClientRects().length)return
    if(previous!==element){lift=0;previous=element}
    const actual=element.getBoundingClientRect()
    const base={left:actual.left,right:actual.right,top:actual.top+lift,bottom:actual.bottom+lift}
    const controls=Array.from(document.querySelectorAll<HTMLElement>('.list-pager button,.list-pager input,.list-pager select'))
      .filter(node=>node.getClientRects().length).map(node=>node.getBoundingClientRect())
    let next=0
    for(let pass=0;pass<8;pass++){
      const overlaps=controls.filter(r=>r.right>base.left-8 && r.left<base.right+8 && r.bottom>base.top-next-8 && r.top<base.bottom-next+8)
      if(!overlaps.length)break
      next=Math.max(next,base.bottom-Math.min(...overlaps.map(r=>r.top))+12)
    }
    next=Math.min(next,Math.max(0,base.top-12))
    if(next!==lift){lift=next;element.style.translate='0 '+(-lift)+'px'}
  }
  function schedule(){if(!frame)frame=requestAnimationFrame(position)}
  onMounted(()=>{
    window.addEventListener('scroll',schedule,true)
    window.addEventListener('resize',schedule)
    observer=new MutationObserver(schedule)
    observer.observe(document.getElementById('app') || document.body,{childList:true,subtree:true})
    schedule()
  })
  onUnmounted(()=>{
    window.removeEventListener('scroll',schedule,true);window.removeEventListener('resize',schedule)
    observer?.disconnect();cancelAnimationFrame(frame)
  })
}
