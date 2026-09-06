Temporary branch-local integration checkpoint.

Pending before Slice 3 can be reviewed as complete:
- wire App.tsx amend/cancel callbacks to PaperLimitOrderMutationController / LiveLimitOrderMutationController;
- remove App-owned liveLimitAttempts map and direct executeLiveLimitAmend/Cancel lifecycle branching;
- retain controller clear on LIVE account/session authority invalidation;
- run targeted tests and production build locally;
- remove this temporary checkpoint file before merge.
