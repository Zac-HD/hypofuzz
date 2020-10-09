# Reading backlog

This note is a dumping point for papers that I might want to put into the literature review.


FUDGE: Fuzz Driver Generation at Scale
https://www.domagoj-babic.com/uploads/Pubs/Fudge/esecfse19fudge.pdf
It's like a fancier ghostwriter for LLVMFuzzOneInput
See also "FuzzGen" - do people at Google actually talk to each other?
https://www.usenix.org/system/files/sec20fall_ispoglou_prepub.pdf

My related work is the ghostwriter
See also also Randoop, Evosuite, https://www.evosuite.org/wp-content/papercite-data/pdf/ase15_faults.pdf


Test data generation by adaptive random testing (section 6)
https://romisatriawahono.net/lecture/rm/survey/software%20engineering/Software%20Testing/Anand%20-%20Automated%20Software%20Test%20Case%20generation%20-%202013.pdf
TLDR; "adaptive random testing" is a whole early-2000s subfield of input generation
where you seek to generate diverse inputs (typically using a distance metric)


TODO: add section on notable PBT tools to literature review
Quickcheck was first
Hedgehog does rose-tree implementation (read up on that)
smallcheck does exhaustive testing
Rudy Matela's thesis for generalisation of failures
link to related ideas in grammar-based fuzzing (by e.g. Andreas Zeller)

model-based stateful testing needs some explication
contrast shrinking/reduction vs normalisation vs generalisation


lots of interest in schema-based testing of web APIs.  See
https://dygalo.dev/blog/schemathesis-progress-report/
https://schemathesis.readthedocs.io/en/stable/index.html
https://github.com/IBM/service-validator is built on top of Schemathesis

https://www.fit.vut.cz/study/thesis/23094/.en - masters thesis based on schemathesis
https://arxiv.org/pdf/1912.09686.pdf - QuickRest, based on Clojure.spec
https://2019.icse-conferences.org/details/icse-2019-Technical-Papers/6/REST-ler-Stateful-REST-API-Fuzzing
https://www.microsoft.com/en-us/research/publication/rest-ler-automatic-intelligent-rest-api-fuzzing/
https://pypi.org/project/fuzz-lightyear/
