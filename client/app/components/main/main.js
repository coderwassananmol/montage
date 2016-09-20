import './main.scss';
import template from './main.tpl.html';

const MainComponent = {
  bindings: {},
  controller: function ($state, userService, versionService) {
    let vm = this;

    userService.getCampaigns().then(data => {
      /*
      if (data.data.status === 'failure') {
        $state.go('login');
        return false;
      }
      */
      vm.user = data.user || {};
    });

    vm.logout = logout;
    vm.showUserMenu = ($mdOpenMenu, ev) => { $mdOpenMenu(ev); };

    versionService.setVersion('blue');

    // functions 

    function logout() {
      userService.logout().then(() => {
        vm.user = {};
        $state.go('login');
      });
    }
  },
  template: template
};

export default () => {
  angular
    .module('montage')
    .component('montMain', MainComponent);
};
