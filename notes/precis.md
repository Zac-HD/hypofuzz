# Business Precis - HypoFuzz


# Summary

I plan to start a small company selling tools for software verification to teams of
software engineers on a subscription basis.  My product (https://hypofuzz.com) is a
category-defining tool with a small but well-defined and well-monied market, extending
a widely used open-source tool (https://hypothesis.works).

Substantial uncertainty about adoption rates (and thus projected revenue) determine
the wide range of possible outcomes, as the unit and marginal costs are favorable
and fixed costs reasonably low.



# Company description
I have formed a company, "ZHD Technologies Pty Ltd", to run the operations for this
venture, while retaining all intellectual property in my own name.  I am the sole
member (shareholder) and director of the company, and expect to be the sole regular
contributor to the business and product for at least the next two years.

In the "growing" scenario (below), David MacIver may join the company.  David founded
the open source Hypothesis project (I am the 'second author'; there are ~200 few-time
contributors) which HypoFuzz is based on.  In the meantime, he will occasionally
contribute his expertise in developing the technology, continue to maintain Hypothesis,
and promote both use of HypoFuzz and the ongoing health of their integration.


## Intellectual property
I am the sole author of and rightsholder in HypoFuzz.  While I am a student at ANU,
students retain sole rights in their work and I have not accepted any scholarship
which could change that.

Hypothesis is published under the Mozilla Public License 2.0, which explicitly permits
commercial use and distribution of larger works under different terms.
See https://choosealicense.com/licenses/mpl-2.0/ for a summary and terms.

In my judgement, HypoFuzz is not patentable in Australia; but it may be worth seeking
a US patent once the business is established.  The main technical innovation is an
effective combination and execution of known techniques rather than a novel invention.


## Notable risks
The most serious risks to a one-person business are related that one person.
This is also my first business, so I expect a steep learning curve; but I have a strong
network to tap for advice and I have served on nonprofit boards since I was 18.

Some - high value - customers will probably ask about succession planning.  I would
like to offer source-code escrow for enterprise customers, as well as having a succession
plan in place for an orderly windup of the company and release of source code in the
event that I am unable to continue running the business.

Economic downturns are not especially risky; clients in tech, financials, etc. are
largely stable and conditional on adoption HypoFuzz is not really a discretionary
product ("let's save 1/20 FTE cost by cutting risk mitigation and product quality").


## Capital requirements
As discussed below ("Financial projections: Costs"), subscription software businesses
are not capital-intensive.  I can fund initial costs out of my personal savings, and
do not intend to take any outside investment.



# Product and market research
HypoFuzz is a software verification tool designed for teams of sophisticated software
engineers using Python.

It is built on top of a free and open-source tool for Python called Hypothesis
(https://hypothesis.works) which I have been working on as co-author since 2017.
This is both an excellent sales channel and chief constraint: HypoFuzz is essentially
an add-on to the open source tool.


## Addressable market
Python is *very* widely used, and still growing, with a large majority of tech companies making
extensive use of Python for data science or their core products.  Including web development and
data science uses, I estimate around a quarter of all large businesses are serious Python users
and around half of those have an approach to software testing which would benefit from HypoFuzz.

The Python Software Foundation annual survey (20,000 respondents) found 4% already using
Hypothesis, and I estimate 40% of respondents *could* use Hypothesis.
Assuming that many Hypothesis users are not professional software developers or are not
in a position to pay for my product, I estimate the immediately addressable market is
between 0.5-1% of Python users and 2-4% of Python-using companies.

Multiplying out by a rough estimate of 50k large businesses globally gives me 120-250
large business prospects, and (more of them * less likely) call it 100-500 prospects
across government, NFP, and medium business.

Based other data I estimate that among current Hypothesis users there are at least
dozens and perhaps as many as tens of thousands of potential customers, so in the short term
growth will come from up-selling users of the free tool.  Long term, company growth will be
driven by growing adoption and use of Hypothesis.


## Competing products
Fuzzing is a well-known technique for finding security problems in low-level languages.
I am not aware of any product or technology which could directly compete with HypoFuzz -
my main challenge is to define and then sell customers on the value of the *category*
rather than my specific product.  (I omit product strategy here in order to keep this
document to a reasonable length)

I am not particularly concerned about new market entrants or potential customers who
choose to build competing tooling in-house.  In either case, they would need to replicate
or at least understand in-depth several person-years of research and development by
PhD-level software engineers; and then pay for ongoing maintainence as the ecosystem
evolves - and the high cost of such expertise is a substantial barrier to entry.
Hypothesis, unlike equivalent tools for other languages, is a 'category-killer'
and does not have any competing libraries in Python.  Indeed, new competitors in other
languages are often explicitly based on Hypothesis!

Google and Microsoft each have an equivalent integrated fuzzing service for low-level
languages, and could conceivably extend them to support Python - but they would also
need to go through Hypothesis to get a good user experience or entirely replace it at
enormous cost.  In both cases I believe a partnership on reasonable terms would be
mutually preferable to competition, but at sufficient cost they *could* duplicate
much of HypoFuzz.


## Adoption of Hypothesis
Hypothesis is very widely in industry, governments, science, and amongst hobbyists.
It is very difficult to get reliable usage numbers for open-source projects, but
notable corporate users include Google, Amazon, Uber, Facebook, Instagram, Stripe,
Bloomberg, and there are many others across financials, energy, health, and research.
See "Direct outreach" under the sales and marketing section, below.


# Financial projections
I entirely ignore the time-value of money, as low interest rates and the short timeframe
make it immaterial compared to the uncertainty in e.g. revenue outcomes.

## Costs
Software-as-a-service is a *very* nice business to be in, particularly if you're not
paying for developers.  It's capital-efficient and has *absurdly* good margins.


### Setup costs

| Cost ($) | Description |
| ---: | :--- |
| 1,645 | Company formation |
| 187 | Domain name registration (ten years) - hypofuzz.com |
| 1,500 | Legal - subscriber agreement |
| *???* | *Graphic design and branding* |
| 3,332 | **total** |

*I've paid most of this out of pocket, but can probably loan the company money
and have it reimburse me.*


### Monthly recurring costs

| Cost ($) | Description |
| ---: | :--- |
| 22 | ASIC registration fee ($254 annually) |
| 8 | Bank Australia account fee |
| 65 | Xero - bookkeeping and invoicing with multi-currency support |
| 9 | Google Workspaces - email, docs, video calls, etc. |
| 13 | GemFury - package hosting / distribution |
| 0 | Github - source code hosting, testing, website backend (free plan for now) |
| **117** | **known monthly total** |
| *??* | Papendrea partners - accounting services (monthly average) |
| *180?* | IT Liability Insurance (PI + PL) - est. 2k - 2.5k annually |
| ***350*** | **estimated monthly total** |

*Note: many of these costs are approximate and rounded due to currency conversion from
USD into AUD, and where noted may be pro-rated from e.g. annual into monthly costs.*

I do not plan to incur discretionary costs (e.g. paid marketing, copywriting, design) until
the business is otherwise profitable and they are credibly linked to marginal revenue growth.

Support costs are minimal; I expect online documentation and in-product hints to cover
most queries.  Remaining issues can be handled by email, though a response SLA would
require a quote and separate contract.


### Other
The final - substantial! - cost is the opportunity cost of my own time; my usual consulting
rate is AUD $300/hour and I would expect to make 150-250k/year working as a full-time
software engineer.  However, I am currently in and enjoying the first year of my PhD in
computer science, and have very tight synergies between my research agenda and product
development.  Between my stipend and personal savings I do not need the company to start
paying me quickly, so long as it otherwise reaches breakeven.


## Revenue
This section is indicative, since I don't actually have any customers yet,
but I believe the broad strokes are reasonably accurate.

Per https://hypofuzz.com/pricing/ I expect to have two broad sources of revenue:

- subscription payments, at USD $99, $249, or $999 per month (or custom enterprise plans)
- related consulting revenue, which I may wish to bill as a sole trader rather than via the company

So the core question is: how many subscription clients can I acquire, over what timeframe,
and at what price?  The 'sales and marketing' section has details, but indicative scenarios
for the first two years:

- "It's a flop" - less than five customers sign up at sustainable price-points.
  I take a personal loss of $X,000 and shut down the company, open source the product
  and find a job after I graduate.  Expensive learning experience but not a disaster.

- "Side project" - 5-20 customers, implying monthly recurring revenue of around $3,000 AUD.
  I take a full-time job but keep the company running as a side project.

- "Sustainable" - 20-100 customers, competitive with post-graduation employment.
  Run the business full time with a view to bringing David (Hypothesis founder)
  on board but otherwise keeping it pretty lean.

- "Growing fast" - adding >100 customers per year, implying annual revenue growth of
  $400K AUD.  This is a very, very good outcome and would support significant
  reinvestment to grow the market and company, though still few (~4?) staff.

Flopping seems unlikely (<20%); I can't rule it out but it would mean I've substantially
underestimated the price-sensitivity of prospects and can't correct with better marketing.
Side project is probably the default outcome if I run this like a hobby instead of a
business - which I don't plan to but might happen anyway; let's call that 30% odds.

Sustainable is my median estimate if I'm pushing hard on the business, ~40% odds.
Fast growth would imply that I've underestimated the rate of update and/or size
of the addressable market (~10% chance).



# Sales and marketing plan

## Value proposition
"Get more value from your existing tests" - computers are a lot cheaper than software
engineers, and HypoFuzz automates part of their work.  An argument from risk mitigation
is also very clear and should be effective in e.g. financial firms (and we have case
studies from Hypothesis I can leverage for this).

This is more a question of effective, and later targeted, communication than of
actually having a solid value proposition.


## Sales and distribution
All sales would be through my own website, using Stripe + Xero to handle payments and
either a hosted or self-managed server for distribution.  Initial setup is currently
manual for each new customer, but automatable with a moderate time investment.

HypoFuzz has a two-part sales funnel; the first is the low-touch funnel into using Hypothesis.
Fortunately, this has been working steadily for years now - it works as-is on the basis of
organic discovery, online documentation, and significant publicity from conferences.
Social media campaigns and documentation overhauls would also help but are low-priority.

Part two is the funnel from Hypothesis user to HypoFuzz customer.  This is presently
short and narrow; as below I plan to start with the website and direct outreach, then
introduce other tactics once I have market feedback to direct them.


## Pricing strategy
My pricing strategy - https://hypofuzz.com/pricing/ - is a standard SAAS three-tier-or-call-us
grid, using higher-end prices because I'm selling something which makes expensive software
engineers more productive.  Higher prices also discourage low-value prospects.

I'm selling by fixed prices for team size, rather than per-user or on a usage basis, largely
because the overhead and user-experience-degredation of monitoring is simply not worth it.
By the nature of the product high-value customers will need to run it on their own
infrastructure anyway, and so while I control distribution usage is out of my hands.

The specific prices are standard, and designed to fit just under common price cutoffs
which require out-of-team approval for the purchase.  The *benefits* of each tier are
a basic exercise in price discrimination and much more likely to evolve over time
(grandfathering existing customers).

Offering a hosted service version is an obvious extension to the business model, but adds
a substantial operational burden and changes the unit economics considerably.  I would
expect to pursue this option in ~2022 if the business takes off as an accessible offering
for smaller clients.


## Direct outreach
I have a partly-assembled list of people who have contributed to Hypothesis and work
for various tech firms; I expect reaching out to them for an informational discussion
will lead to several sales.  It will also help shape the feature roadmap and could
substantially improve my messaging on the website.

After the initial push I can keep this up on a rolling basis for new prospects.


## Passive online marketing
Linking to HypoFuzz from the documentation for Hypothesis (the free tool) can generate
considerable exposure and *if tasteful* work well - just need to be careful to balance
visibility against annoyance for non-prospects and possible perceptions of 'selling out'.

(open source communities are occasionally supported and frequent exploitated by
for-profit entities, and community backlash could seriously impair the company.
I personally, and the Hypothesis project, have significant goodwill of unclear commercial value; and I would expect that to transfer to HypoFuzz unless badly mismanaged.)

Content marketing, i.e. educational material produced to drive traffic to the website,
will be an effective strategy for such a specialised product.  However, given the
required investment of time to write (or money to have written) I do not plan more than
occasional posts at this time.

I am also a regular speaker at Python conferences, and use them to raise awareness
of Hypothesis and where relevant promote HypoFuzz.  So far in 2020 I've had talks accepted
by conferences in Russia, Italy, the USA (x2), Australia, and India.


## Sponsorships or paid marketing
Plausibly effective, including cost-effective if targeted well (hard in this case).
However it's hard to justify the costs before I have a healthy initial customer base
and clear success stories to promote.

Sponsoring open-source developers, projects, conferences, foundations, etc. would
also be a very effective brand promotion exercise.  Again though, it's hardly worth
writing a CSR policy at the pre-revenue stage.
