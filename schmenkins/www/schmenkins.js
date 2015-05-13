var schmenkinsApp = angular.module('schmenkinsApp', ['ngRoute']); 

schmenkinsApp.config(['$routeProvider',
  function($routeProvider) {
    $routeProvider.
      when('/jobs', {
        templateUrl: 'partials/jobs.html',
        controller: 'JobListController'
      }).
      when('/jobs/:jobName', {
        templateUrl: 'partials/job-detail.html',
        controller: 'JobDetailController'
      }).
      when('/jobs/:jobName/:buildId', {
        templateUrl: 'partials/build-detail.html',
        controller: 'BuildDetailController'
      }).
      otherwise({
        redirectTo: '/jobs'
      });
  }]);

schmenkinsApp.controller('JobListController', function($scope, $http) {
  $http.get('/summary.json?fresh=' + Date.now()).success(function (data) {
    $scope.summary = data;
  });
});
