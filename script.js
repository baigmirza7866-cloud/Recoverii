const header = document.getElementById('header');
window.addEventListener('scroll', () => {
  header.classList.toggle('scrolled', window.scrollY > 60);
});

function toggleMenu() {
  document.getElementById('navLinks').classList.toggle('open');
}
function closeMenu() {
  document.getElementById('navLinks').classList.remove('open');
}

document.addEventListener('click', (e) => {
  const nav = document.querySelector('.nav');
  if (!nav.contains(e.target)) closeMenu();
});

document.addEventListener('DOMContentLoaded', () => {
  const days = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
  const today = days[new Date().getDay()];
  document.querySelectorAll('.hours-table tr').forEach(row => {
    if (row.cells[0] && row.cells[0].textContent.trim() === today) {
      row.style.background = '#fff3f3';
      row.cells[0].style.color = '#c0392b';
      row.cells[0].style.fontWeight = '700';
      row.cells[1].style.color = '#c0392b';
      row.cells[1].style.fontWeight = '600';
    }
  });

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.style.opacity = '1';
        entry.target.style.transform = 'translateY(0)';
      }
    });
  }, { threshold: 0.1 });

  document.querySelectorAll('.service-card, .review-card, .gallery-item').forEach(el => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(20px)';
    el.style.transition = 'opacity .4s ease, transform .4s ease';
    observer.observe(el);
  });
});