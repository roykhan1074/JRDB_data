(function () {
  const NAV_LINKS = [
    { href: '/download.html', label: 'データ取込', frequent: true },
    { href: '/search.html',   label: 'レース検索', frequent: true },
    { href: '/watchlist.html',    label: 'ウォッチリスト', frequent: true },
    { href: '/analyze.html',  label: '回収率分析' },
    { href: '/jockey-ninki.html', label: '騎手×人気偏差' },
    { href: '/course.html',       label: 'コース別傾向' },
    { href: '/factor-recovery.html', label: '指数帯別回収率' },
    { href: '/stats.html',    label: 'データ確認' },
  ];

  const path = window.location.pathname.replace(/\/$/, '') || '/';

  const logoSvg = `<svg width="18" height="18" viewBox="0 0 22 22" fill="none" style="flex-shrink:0">
    <circle cx="9" cy="9" r="7" stroke="white" stroke-width="1.8"/>
    <path d="M5.5 11L7.5 7.5L10 10L12 6.5" stroke="#f0c040" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="14" y1="14" x2="20.5" y2="20.5" stroke="white" stroke-width="2.2" stroke-linecap="round"/>
  </svg>`;

  const items = NAV_LINKS.map(l => {
    const active = path === l.href || path === l.href.replace('.html', '');
    const classes = [active ? 'nav-active' : '', l.frequent ? 'nav-frequent' : ''].filter(Boolean).join(' ');
    return `<li><a href="${l.href}"${classes ? ` class="${classes}"` : ''}>${l.label}</a></li>`;
  }).join('');

  const nav = document.createElement('nav');
  nav.className = 'site-nav';
  nav.innerHTML = `
    <a class="nav-logo" href="/">${logoSvg}RACE INSIGHT</a>
    <ul class="nav-links">${items}</ul>
  `;

  const header = document.querySelector('header');
  if (header) {
    header.innerHTML = '';
    header.appendChild(nav);
  }
})();
