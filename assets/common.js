/* Общие элементы всех страниц Metod VIPBET: подтверждение возраста 18+ и уведомление о cookies. */
(function () {
  var ROOT = new URL('..', document.currentScript.src).href;
  function get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }

  function cookieBar() {
    if (get('vip-cookies')) return;
    var bar = document.createElement('div');
    bar.className = 'cookie';
    bar.setAttribute('role', 'region');
    bar.setAttribute('aria-label', 'Уведомление о cookies');
    bar.innerHTML = '<span>Мы используем cookies и хранилище браузера, чтобы сайт работал быстрее. Подробнее — в <a href="' + ROOT + 'privacy.html">политике конфиденциальности</a>.</span>' +
      '<button class="btn btn-gold" type="button">Понятно</button>';
    bar.querySelector('button').onclick = function () { set('vip-cookies', '1'); bar.remove(); };
    document.body.appendChild(bar);
  }

  function ageGate() {
    if (get('vip-age18')) { cookieBar(); return; }
    var d = document.createElement('dialog');
    d.className = 'agegate';
    d.setAttribute('aria-labelledby', 'ageTitle');
    d.innerHTML = '<div class="age-in"><img src="' + ROOT + 'assets/vipbet-logo.jpg" alt="" width="88" height="88">' +
      '<h2 id="ageTitle">Вам есть 18 лет?</h2>' +
      '<p>Сайт содержит информацию о ставках на спорт и предназначен только для совершеннолетних.</p>' +
      '<div class="row"><button class="btn btn-gold" type="button" data-yes>Да, мне есть 18</button><button class="btn btn-ghost" type="button" data-no>Нет</button></div></div>';
    document.body.appendChild(d);
    d.addEventListener('cancel', function (e) { e.preventDefault(); });
    d.querySelector('[data-yes]').onclick = function () { set('vip-age18', '1'); d.close(); d.remove(); cookieBar(); };
    d.querySelector('[data-no]').onclick = function () {
      d.querySelector('.age-in').innerHTML = '<h2>Доступ ограничен</h2><p>Информация о ставках на спорт доступна только лицам старше 18 лет.</p>';
    };
    try { d.showModal(); } catch (e) { d.setAttribute('open', ''); }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ageGate); else ageGate();
})();
