import {installMenus} from './navigation.mjs';

installMenus();

// Make only equations wider than their column into keyboard-accessible scroll regions.
const article = document.querySelector('.chapter');
const displays = article.querySelectorAll('.math-scroll');
const inlines = article.querySelectorAll('p math[display="inline"]');

function makeScrollable(element, enabled) {
  if (enabled) {
    element.tabIndex = 0;
    element.setAttribute('role', 'region');
    element.setAttribute('aria-label', 'Scrollable equation');
  } else {
    for (const name of ['tabindex', 'role', 'aria-label']) element.removeAttribute(name);
  }
}

function fitEquations() {
  for (const box of displays) makeScrollable(box, box.scrollWidth > box.clientWidth + 1);
  for (const math of inlines) {
    const paragraph = math.closest('p');
    const wide = math.getBoundingClientRect().width > paragraph.clientWidth + 1;
    const wrapper = math.parentElement;
    if (wide && !wrapper.classList.contains('inline-scroll')) {
      const scroll = document.createElement('span');
      scroll.className = 'inline-scroll';
      math.before(scroll);
      scroll.append(math);
      makeScrollable(scroll, true);
    } else if (!wide && wrapper.classList.contains('inline-scroll')) {
      wrapper.replaceWith(math);
    }
  }
}

if ('ResizeObserver' in window) new ResizeObserver(fitEquations).observe(article);
window.addEventListener('resize', fitEquations);
document.fonts.ready.then(fitEquations);
fitEquations();
