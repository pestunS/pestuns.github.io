export function installMenus() {
  const menus = [...document.querySelectorAll('.header-menus details')];
  for (const menu of menus) {
    menu.addEventListener('toggle', () => {
      if (menu.open) for (const sibling of menus) if (sibling !== menu) sibling.open = false;
    });
    menu.addEventListener('keydown', event => {
      if (event.key !== 'Escape') return;
      menu.open = false;
      menu.querySelector('summary').focus();
    });
  }
  document.addEventListener('click', event => {
    for (const menu of menus) if (!menu.contains(event.target)) menu.open = false;
  });
  const sectionLinks = [...document.querySelectorAll('[data-section]')];
  const sectionIds = new Set(sectionLinks.map(link => link.dataset.section));
  const sections = [...sectionIds].map(id => document.getElementById(id)).filter(Boolean);
  const layoutLinks = [...document.querySelectorAll('[data-layout-link]')];
  const header = document.querySelector('.masthead');
  let queued = false;
  let chosen = sections.find(heading => '#' + heading.id === location.hash);

  function trackPosition() {
    queued = false;
    const limit = header.getBoundingClientRect().bottom + 64;
    const bottom = window.scrollY > 1 && Math.ceil(window.scrollY + window.innerHeight) >= document.documentElement.scrollHeight - 2;
    const byScroll = bottom ? sections.at(-1) : sections.filter(heading => heading.getBoundingClientRect().top <= limit).at(-1);
    const active = chosen || byScroll;
    for (const link of sectionLinks) {
      if (active && link.dataset.section === active.id) link.setAttribute('aria-current', 'location');
      else link.removeAttribute('aria-current');
    }
    for (const link of layoutLinks) link.hash = active ? active.id : '';
  }
  function schedule() {
    if (!queued) {queued = true; requestAnimationFrame(trackPosition);}
  }
  window.addEventListener('scroll', schedule, {passive: true});
  window.addEventListener('resize', schedule);
  window.addEventListener('pageshow', schedule);
  window.addEventListener('hashchange', () => {
    chosen = sections.find(heading => '#' + heading.id === location.hash);
    schedule();
  });
  function followScroll(event) {
    if (!header.contains(event.target)) {chosen = null; schedule();}
  }
  document.addEventListener('wheel', followScroll, {passive: true});
  document.addEventListener('touchmove', followScroll, {passive: true});
  document.addEventListener('keydown', event => {
    if (['PageUp','PageDown','Home','End',' '].includes(event.key)) followScroll(event);
  });
  for (const link of sectionLinks) link.addEventListener('click', () => {
    chosen = document.getElementById(link.dataset.section);
    trackPosition();
    const menu = link.closest('details');
    if (menu) {
      menu.open = false;
      const heading = document.getElementById(link.dataset.section);
      heading.tabIndex = -1;
      heading.focus({preventScroll: true});
    }
  });
  trackPosition();
}
