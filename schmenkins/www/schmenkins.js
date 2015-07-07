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

schmenkinsApp.controller('JobListController', function($scope, $http) {
  $scope.now = Date.now();
  $scope.builds = [];
  $http.get(baseUrl + '/recent_builds.json?fresh=' + Date.now()).success(function (recent_builds) {
    $http.get(baseUrl + '/summary.json?fresh=' + Date.now()).success(function (summary) {
      debugger;
      for (idx in recent_builds) {
        build = recent_builds[idx];
        more_info = summary['all_builds'][build['job']][build['id']];
        for (k in more_info) {
          build[k] = more_info[k];
        }
      }
      $scope.builds = recent_builds;
    });
  });
});

schmenkinsApp.controller('JobDetailController', function($scope, $routeParams, $http) {
  $scope.jobName = $routeParams.jobName;
  $scope.builds = {};
  $http.get(baseUrl + '/jobs/' + $routeParams.jobName + '/state.json').success(function (data) {
    $scope.job = data;
    for (idx=$scope.job.last_build.id;idx>0;idx--) {
      $http.get(baseUrl + '/jobs/' + $routeParams.jobName + '/build_records/' + idx + '/state.json').success(function (data) {
        $scope.builds[data.id] = data;
      });
    }
  });
  $http.get(baseUrl + '/jobs/' + $routeParams.jobName + '/build_records/' + $routeParams.buildId + '/consoleLog.txt').success(function (data) {
    $scope.consoleLog = data;
  });
});

schmenkinsApp.controller('BuildDetailController', function($scope, $routeParams, $http) {
  $scope.jobName = $routeParams.jobName;
  $http.get(baseUrl + '/jobs/' + $routeParams.jobName + '/build_records/' + $routeParams.buildId + '/state.json?fresh=' + Date.now()).success(function (data) {
    $scope.build = data;
  });
  $http.get(baseUrl + '/jobs/' + $routeParams.jobName + '/build_records/' + $routeParams.buildId + '/consoleLog.txt').success(function (data) {
    $scope.consoleLog = data;
  });
});
