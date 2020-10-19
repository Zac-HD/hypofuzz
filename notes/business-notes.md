# hypofuzz business notes

TODO: update landing page, add image (of dashboard), add Hypothesis testimonials

TODO: use a static site generator to generate the frontpage, pricing page, etc.
or on investigation, just write HTML, Pelican is rather blog-focussed and I have
rather few non-docs pages.

GitLab has a nice fuzzing roadmap:
https://about.gitlab.com/direction/secure/fuzz-testing/fuzz-testing/


## Corporate structure

TBC, but likely to be whatever makes sense as a small Australian business.

TODO: insurance, accounting, tax advice, etc.


An explicit goal is to keep options open for a (relatively) painless sale later;
while unlikely it's not much more expensive and mostly good discipline anyway.



### Payments system

TODO: set up Stripe to take payments


### Distribution

Is currently via GemFury's PyPI support, though long term I'd like to move to something
customised which can give me more detailed analytics, etc.  This might actually be
pretty easy to do if I'm already running a webserver for Stripe integration.

See https://gemfury.com/help/pypi-server
It's already aliased to packages.hypofuzz.com/pypi

Test access token: 1GVNXw-JKMinWjFBpDYcrgTwQ8nEl35wA0 to be used as

    pip install --extra-index-url=https://1GVNXw-JKMinWjFBpDYcrgTwQ8nEl35wA0:@packages.hypofuzz.com/pypi/ hypofuzz


### Other services

https://search.google.com/search-console/sitemaps?resource_id=https%3A%2F%2Fhypofuzz.com%2F
https://analytics.google.com/analytics/web/#/
https://mailchimp.com/


### Split with David

Talking to David MacIver on 2020-09-19, we talked over the general principles of running
a commercial offering based on an open source project.  He has minimal extra availability,
but we agreed that a 1/3 profit assignment is fair in light of past and future work
on Hypothesis enabling HypoFuzz to exist at all.

See https://mail.google.com/mail/u/0/?shva=1#sent/QgrcJHrnwgwrcxKSMNVSRVQQvxbNHHswHdv



## Website design etc.

https://getbootstrap.com/ for basic CSS and JS
Then Flatly theme from https://bootswatch.com/flatly/ replaces bootstrap.min.css
And then go to boostrap examples to copy and paste snippets and assembly webpage.

For human-oriented graphics, open source, https://www.humaaans.com/

https://saaspages.xyz/ collects examples of standard pages from SAAS businesses

https://www.checklist.design/ is, well, design checklists
