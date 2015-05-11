# Schmenkins

Out of sheer frustration trying to automate deploying Jenkins, I wrote Schmenkins instead.

I didn't want to convert all my configuration from jenkins-job-builder to something else, so those are just Schmenkins' native configuration.

Here's how to use Schmenkins:

    $ pip install schmenkins
    $ schmenkins statedir jenkins-jobs/everything.yaml

That's it, really.

Schmenkins remembers when it was last run. If anything was supposed to have run since then (SCM polling, for instance) it gets run. So just stick Schmenkins in a cron job and you're in a good shape.

Of course it doesn't support everything Jenkins supports or even everything jenkins-job-builder supports. I've just added that few features that I need for myself. This includes (and is actually limited to):

Project types:
 * Freestyle

Builders:
 * shell
 * copyartifacts

Reporters:
None

Publishers:
 * artifacts
 * trigger-parameterized-builds

SCM:
 * git

Triggers:
 * Poll SCM
 * Timed

Wrappers:
None

