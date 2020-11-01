# Launch Plan - Nov-Dec 2020

As of late October, ZHD Technologies Pty Ltd exists (!), and so it's time to
work out the launch plan.  At a high level, this involves:

- Pre-launch setup and conversations
- "Soft launch", building up automation and organic growth drivers
- "Public launch", the low-marginal-input steady state

The remainder of this document goes into more detail about each phase of the
launch, and will later include some notes about how it went.


## 0-1: Finish setup, early conversations
The goal of this stage: go from "owning a company" to "running a small business".

Specifically, that means that ZHD Tech. can and does take money from one customer
to deliver a product.  In turn, that means that the priorities are to

- [x] set up GSuite for emails like sales@hypofuzz.com
- [x] get a business bank account
    - [x] Talk to Kathy, Bendigo, Bank Aus, Papendrea; choose account
    - [x] Set up account (transaction + savings) and make initial deposit
    - [ ] Configure GSuite billing
    - [ ] Configure Xero billing
    - [x] Ask Papendrea about GST registration (-> do it later)
    - [x] Ask re super, wages, etc (-> do it later; just take distributions
      while small.  NB check this makes sense given minimal income)
- [x] Xero subscription for bookeeping and invoicing
    - [x] Send form to set up bank feeds
    - [x] Set up chart of accounts (added SAAS, sponsorships, and revenue sources)
    - [ ] Talk to Gianmarco about
        - What other setup should I be doing?
        - What legal advice / drafting do I need?
        - What insurance do I need?
    - [ ] Get first-pass logos and colourscheme etc done for website and invoices
- [ ] get legal policies done
  (privacy policy, subscription terms, etc.; some standard but not all)
- [ ] get whatever insurance I need

Before that's finished, I also want to start some conversations with highly
qualified leads on corporate dev teams about

- Non-negotiable features (e.g. `unittest` support)
- 'Killer features' which would result in an immediate sale
- How HypoFuzz would fit into their development cycle (who uses it and when)
- What questions the documentation doesn't answer
- Would you help with feedback, research (bug numbers), a testimonial?

Specific people to reach out to - mostly prominent open source Hypothesis users
at tech companies:

- [x] Instagram's LibCST team
- [x] Paul Ganssle @ Google New York
- [x] Uber engineering (follows gufuncs blog post; bounced - follow up later)
- [x] Yelp `fuzz-lightyear` team (turns out they don't use Hypothesis much)
- [x] Nelson Elhage (for general feedback and backlinks)
- [x] Dan Luu (general feedback, links, other people)
- [x] each of the Mailchimp signups
- ??? who else should I get in touch with personally?




## Soft Launch: cover costs and confirm viability
The goal of this stage is to validate basic product-market fit, cover recurring
costs, and get ready for public launch.  Tactically, this includes resolving any
serious customer objections, and skipping as much of the 'saas ramp' as possible
by doing things that don't scale to acquire early customers.


### Build inbound links
This drives credibility, long-term customer acquisition, and hands-off growth.

- [ ] Sprinkle links through Hypothesis documentation where appropriate
- [x] Add links to my personal site
- [x] Check 'Stop Writing Tests' talk descriptions
- [ ] Ask Louise, ?? to proofread website
- Reach out to ask bloggers who wrote about Hypothesis + Fuzzing for a link
    - [x] https://danluu.com/testing/
    - [x] https://blog.nelhage.com/post/property-testing-is-fuzzing/
      and https://blog.nelhage.com/post/property-testing-like-afl/
    - [ ] https://hypothesis.works/articles/what-is-property-based-testing/
      (might want to get the whole website into the monorepo first)
    - ???


### Automate onboarding
Reducing the marginal cost in my time to onboard a customer is nice,
but the real goal is minimal friction (ie sales funnel losses).

- [ ] Set up a Stripe-based checkout flow
- [ ] Automatic key issuance - does this need different distribution?


## More outreach
Directed outreach to qualified leads i.e. Hypothesis users.  Corporate users
get a "hey you use Hypothesis, why not fuzz your tests" sales pitch.
Credible non-commercial users get "are you interested in a free licence,
I'd love to hear what you think" and then asked for blog post/link/testimonial
if they take it up.  Small OSS projects don't get contacted.

- [ ] Hypothesis mailing list - DRMacIver can send out via Tinyletter
- [ ] Search GitHub and libraries.io
- [ ] Email my GitHub followers
- [ ] PyPy, CPython (via Paul Ganssle, Terry Reedy), Enthought/NumFocus
- ???




## Public launch
*Goal: scale up, profit, minimise marginal work per customer.*

The defining feature of this stage is **low-touch sales**: I no longer feel that
I need to "do things that don't scale" to keep things rolling at an acceptable
rate (though I might choose to anyway, as an accelerator).

- [ ] Talk to Kathy about getting tech media coverage
- Post links on
    - [ ] Reddit (fuzzing, python, programming)
    - [ ] news.ycombinator.com ("Show HN")
    - [ ] producthunt.com
    - [ ] Twitter
    - [ ] Python testing newsletters, podcasts, etc.
    - ???
- [ ] Consider general/local media coverage?
- [ ] Get a contractor to improve website and dashboard?
- [ ] Scale up content marketing plan, landing pages, etc.
- ???
