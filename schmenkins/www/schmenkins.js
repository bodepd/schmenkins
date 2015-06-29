var schmenkinsApp = angular.module('schmenkinsApp', ['ngRoute', 'filter.duration']); 

var baseUrl = ''; // http://overcastcloud.com/schmenkins';

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

function getSuccesHandler(scope, idx) {
  return function (data) {
    for (k in data) {
      scope.builds[idx][k] = data[k];
    }
  }
}

schmenkinsApp.controller('JobListController', function($scope, $http) {
  $scope.now = Date.now();
  $scope.builds = [];
  $http.get(baseUrl + '/state/recent_builds.json?fresh=' + Date.now()).success(function (data) {
    $scope.builds = data;
    for (idx in data) {
      build = data[idx];
      $http.get(baseUrl + '/state/jobs/' + build.job + '/build_records/' + build.id + '/state.json?fresh=' + Date.now())
           .success(getSuccesHandler($scope, idx));
    }
  });
});

schmenkinsApp.controller('JobDetailController', function($scope, $routeParams, $http) {
  $scope.jobName = $routeParams.jobName;
  $scope.builds = {};
  $http.get(baseUrl + '/state/jobs/' + $routeParams.jobName + '/state.json').success(function (data) {
    $scope.job = data;
    for (idx=$scope.job.last_build.id;idx>0;idx--) {
      $http.get(baseUrl + '/state/jobs/' + $routeParams.jobName + '/build_records/' + idx + '/state.json').success(function (data) {
        $scope.builds[data.id] = data;
      });
    }
  });
  $http.get(baseUrl + '/state/jobs/' + $routeParams.jobName + '/build_records/' + $routeParams.buildId + '/consoleLog.txt').success(function (data) {
    $scope.consoleLog = data;
  });
});

schmenkinsApp.controller('BuildDetailController', function($scope, $routeParams, $http) {
  $scope.jobName = $routeParams.jobName;
  $http.get(baseUrl + '/state/jobs/' + $routeParams.jobName + '/build_records/' + $routeParams.buildId + '/state.json?fresh=' + Date.now()).success(function (data) {
    $scope.build = data;
  });
  $http.get(baseUrl + '/state/jobs/' + $routeParams.jobName + '/build_records/' + $routeParams.buildId + '/consoleLog.txt').success(function (data) {
    $scope.consoleLog = data;
  });
});
