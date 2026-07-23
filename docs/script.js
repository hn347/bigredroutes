const menuButton = document.querySelector('.menu-toggle');
const navigation = document.querySelector('.site-nav');

if (menuButton && navigation) {
  const closeMenu = () => {
    navigation.classList.remove('is-open');
    menuButton.setAttribute('aria-expanded', 'false');
  };

  menuButton.addEventListener('click', () => {
    const isOpen = navigation.classList.toggle('is-open');
    menuButton.setAttribute('aria-expanded', String(isOpen));
  });

  navigation.querySelectorAll('a').forEach((link) => {
    link.addEventListener('click', closeMenu);
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      closeMenu();
      menuButton.focus();
    }
  });
}
