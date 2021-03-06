const AlertService = ($mdToast) => {
  const toast = $mdToast.simple()
    .highlightClass('md-accent')
    .toastClass('toast__top')
    .position('bottom left');

  const service = {
    success: (text, time) => {
      toast
        .textContent(text)
        .hideDelay(time || 1000);
      $mdToast.show(toast);
    },
    error: (error, time) => {
      const text = error.data
        ? `${error.data.message}: ${error.data.detail}`
        : null;

      if (!text) { return; }
      toast
        .textContent(text)
        .hideDelay(time || 5000);
      $mdToast.show(toast);
    },
  };

  return service;
};

export default AlertService;
