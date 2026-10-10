/* Top menu: dropdown panels open on click (and on hover with a mouse), close on Escape or a click outside.
   On narrow screens the Menu button shows the whole list. */
(function () {
  var nav = document.getElementById('siteNav');
  if (!nav) return;
  var triggers = Array.prototype.slice.call(nav.querySelectorAll('.nav-trigger'));
  var menu = document.getElementById('navMenu'), toggle = nav.querySelector('.nav-toggle');
  var hover = window.matchMedia('(hover: hover) and (min-width: 901px)');

  function panelOf(t) { return document.getElementById(t.getAttribute('aria-controls')); }
  function close(t) { t.setAttribute('aria-expanded', 'false'); panelOf(t).hidden = true; }
  function closeAll(except) { triggers.forEach(function (t) { if (t !== except) close(t); }); }
  function open(t) { closeAll(t); t.setAttribute('aria-expanded', 'true'); panelOf(t).hidden = false; }

  triggers.forEach(function (t) {
    var item = t.parentNode, timer;
    t.addEventListener('click', function () { t.getAttribute('aria-expanded') === 'true' ? close(t) : open(t); });
    item.addEventListener('mouseenter', function () { if (hover.matches) { clearTimeout(timer); open(t); } });
    item.addEventListener('mouseleave', function () { if (hover.matches) timer = setTimeout(function () { close(t); }, 180); });
  });
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    var openT = triggers.filter(function (t) { return t.getAttribute('aria-expanded') === 'true'; })[0];
    if (openT) { close(openT); openT.focus(); }
    else if (menu.classList.contains('open')) { menu.classList.remove('open'); toggle.setAttribute('aria-expanded', 'false'); toggle.focus(); }
  });
  document.addEventListener('click', function (e) { if (!nav.contains(e.target)) { closeAll(); } });
  if (toggle) toggle.addEventListener('click', function () {
    var on = !menu.classList.contains('open');
    menu.classList.toggle('open', on); toggle.setAttribute('aria-expanded', String(on));
    if (!on) closeAll();
  });
})();
