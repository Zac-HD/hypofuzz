# hypofuzz business notes

TODO: update landing page, add image (of dashboard), add Hypothesis testimonials

TODO: use a static site generator to generate the frontpage, pricing page, etc.
or on investigation, just write HTML, Pelican is rather blog-focussed and I have
rather few non-docs pages.

GitLab has a nice fuzzing roadmap:
https://about.gitlab.com/direction/secure/fuzz-testing/fuzz-testing/


## Corporate structure

"ZHD Technologies Pty Ltd" is the operating entity; I (Zac) personally retain all
intellectual property rights.

TODO: insurance, accounting, tax advice, etc.


An explicit goal is to keep options open for a (relatively) painless sale later;
while unlikely it's not much more expensive and mostly good discipline anyway.



### Payments system

Using Stripe 'payment links' https://dashboard.stripe.com/payment-links
for a no-code checkout.  Each standard tier is set up as a separate "product"
with recurring billing.


### Distribution

Is currently via PyPI support, though long term I'd like to move to something
customised which can give me more detailed analytics, etc.  This might actually be
pretty easy to do if I'm already running a webserver for Stripe integration.

    pip install hypofuzz


### Other services

https://search.google.com/search-console/sitemaps?resource_id=https%3A%2F%2Fhypofuzz.com%2F
https://analytics.google.com/analytics/web/#/
https://mailchimp.com/


To send announcements via https://tinyletter.com/DRMacIver/archive
email them to beamer-4b1ffbf69f7ae89ffe2cb1cb053537da3fbedf7a@tinyletter.com


### Split with David

Talking to David MacIver on 2020-09-19, we talked over the general principles of running
a commercial offering based on an open source project.  He has minimal extra availability,
but we agreed that a 1/3 profit assignment is fair in light of past and future work
on Hypothesis enabling HypoFuzz to exist at all.

See https://mail.google.com/mail/u/0/?shva=1#sent/QgrcJHrnwgwrcxKSMNVSRVQQvxbNHHswHdv

Subsequently he decided not to be involved initially, due to other committments and the
tax and other paperwork issues involved in trans-national business ownership.



## Website design etc.

Emails should also follow graphic and brand guidelines

https://getbootstrap.com/ for basic CSS and JS
Then Flatly theme from https://bootswatch.com/flatly/ replaces bootstrap.min.css
And then go to boostrap examples to copy and paste snippets and assembly webpage.

For human-oriented graphics, open source, https://www.humaaans.com/

https://saaspages.xyz/ collects examples of standard pages from SAAS businesses

https://www.checklist.design/ is, well, design checklists
