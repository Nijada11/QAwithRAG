# Answers: improved 250w hybrid

Chunks 250 words, retrieval `hybrid`, model `claude-haiku-5-5`, judge `claude-sonnet-5-5`.

| Metric | Value |
|---|---|
| Correct (of 41 answerable) | 98% |
| Correct or partial | 100% |
| Evidence passage retrieved (top 5) | 95% |
| Evidence passage cited (exact phrase) | 93% |
| Answers grounded in their citations | 85% |
| False "I don't know" | 0% |
| "I don't know" on unanswerable (6) | 100% |
| Avg tokens in / out | 4441 / 510 |
| Cost per 1,000 questions | $0.70 |
| Latency p50 / p95 | 2.9 s / 4.4 s |
| Avg retrieval / LLM time | 40 ms / 2.8 s |

## Per question

| id | verdict | cited evidence | question |
|---|---|---|---|
| q01 | correct | yes | What's the longest a Temporary Access Pass can be valid for? |
| q02 | correct | yes | How many wrong password attempts does it take before smart lockout locks an account in a normal commercial tenant? |
| q03 | correct | yes | A user got locked out by smart lockout. If they reset their password with 'I forgot my password', do they still have to wait for the lockout to run out? |
| q04 | correct | yes | Do passwords of users synced with password hash sync expire in Entra ID? |
| q05 | correct | yes | Which password reset policy applies to admin accounts, and can admins use security questions to reset? |
| q06 | correct | yes | We disabled self-service password reset for administrators. How long before that change applies? |
| q07 | correct | yes | By default, how often are users asked to sign in again? |
| q08 | correct | yes | Why does Microsoft recommend blocking legacy authentication protocols? |
| q09 | partial | yes | Is there a way to see what a Conditional Access policy would do before turning it on? |
| q10 | correct | yes | How many words can we put on our custom banned password list? |
| q11 | correct | yes | Can we switch off Microsoft's global banned password list? |
| q12 | correct | yes | How long can a custom security question for password reset be? |
| q13 | correct | yes | When will security questions stop working for self-service password reset? |
| q14 | correct | yes | I revoked a user's sessions. How long can the access token they already have keep working? |
| q15 | correct | yes | How many custom domain names can one tenant have? |
| q16 | correct | yes | Is there a limit to how many dynamic membership groups a tenant can have? |
| q17 | correct | yes | I changed the rule of a dynamic group but its members haven't updated. How long can that take? |
| q18 | correct | yes | How many groups can a memberOf dynamic group rule reference? |
| q19 | correct | yes | We restricted what guest users can see in the directory. When does that take effect? |
| q20 | correct | yes | What counts as an inactive guest in the inactive guest report? |
| q21 | correct | yes | How far back can I see Conditional Access policy changes in the audit log? |
| q22 | correct | yes | If a Conditional Access policy has several grant controls ticked, does the user have to satisfy all of them? |
| q23 | correct | yes | Does number matching work for Authenticator push notifications on an Apple Watch? |
| q24 | correct | - | What kind of hardware OATH tokens does Entra ID support? |
| q25 | correct | yes | Can B2B guest users sign in with SMS as their first factor? |
| q26 | correct | yes | How many people can use Windows Hello for Business on the same PC? |
| q27 | correct | yes | In combined MFA and SSPR registration, which methods are users shown by default? |
| q28 | correct | - | What happens to Conditional Access policies if Entra ID has an outage? |
| q29 | correct | yes | If I create a Conditional Access policy from a template, is it enforced right away? |
| q30 | correct | yes | How many authentication contexts can we define for Conditional Access? |
| q31 | correct | yes | What's the character limit for a filter for devices rule? |
| q32 | correct | yes | In a brand-new tenant, which methods are turned on in the Authentication methods policy? |
| q33 | correct | yes | Does SSPR password writeback work while staged rollout is enabled? |
| q34 | correct | yes | Can users see the custom security attributes on their own profile? |
| q35 | correct | yes | A user restored Authenticator from a backup on a new phone and their work account says 'Sign in to add your account'. Is something wrong? |
| q36 | correct | yes | Account recovery can't match a user against the identity verification provider. What should I check on the user object? |
| q37 | correct | yes | Do users get the app name and location in their MFA prompt when signing in through the NPS extension? |
| q38 | correct | - | Can an admin look up a user's answers to their password reset security questions? |
| q39 | correct | yes | Without any Conditional Access policy, do users need MFA to register a passkey? |
| q40 | correct | yes | Why can't I delete one of our named locations? |
| q41 | correct | yes | Can admins add security questions as a password reset method for themselves? |
| u01 | correct | - | How do I reset a user's password in Google Workspace? |
| u02 | correct | - | What is the maximum mailbox size in Exchange Online? |
| u03 | correct | - | How do I recover a deleted Microsoft Teams chat message? |
| u04 | correct | - | What is the phone number of Microsoft support in Germany? |
| u05 | correct | - | How do I set up a printer for a user with Intune? |
| u06 | correct | - | How many euros per user per month does Microsoft Entra ID P2 cost? |

### q09: partial
**Q:** Is there a way to see what a Conditional Access policy would do before turning it on?  
**Reference:** Yes, report-only mode: policies are evaluated at sign-in but not enforced, so admins can assess impact. It doesn't work for policies scoped to User Actions.  
**Judge:** The answer correctly identifies report-only mode and says it works for 'most' policies, but it never states that policies are evaluated at sign-in but not enforced, and it omits the explicit User Actions exclusion. It also doesn't say the policy is evaluated at sign-in. 'Most policies' hints at a limitation but doesn't name User Actions, so the key caveat is missing. Grounding: several claims are unsupported by the cited passages: 'Results appear in the sign-in log, where you can review the Conditional Access and Report-only tabs' (passage 4 mentions sign-in logs but not the tabs, and it is attached to [2]); 'Policies created from templates also start in this mode' is not in passage 2, which says only 'by default, each policy is created in report-only mode'. So not fully grounded.

> Yes. Two main options let you evaluate a policy before it affects users:
> 
> 1. **Report-only mode.** Administrators can test most policies in this state, and it doesn't enforce them. Report-only mode is a policy state that lets administrators test most Conditional Access policies before enabling them.[1] Results appear in the sign-in log, where you can review the Conditional Access and Report-only tabs. Policies created from templates also start in this mode. By default, each policy is created in report-only mode.[2]
> 
> 2. **The What If tool.** This tool simulates a sign-in for a chosen user, agent identity, or single-tenant service principal, and estimates how your policies would apply. The simulation estimates how your policies affect this sign-in and generates a report.[3] It's useful for checking uncommon scenarios without repeating test sign-ins. Note that it has a limit: the What If tool doesn't test for Conditional Access service dependencies.[3]
> 
> For a broader view across many sign-ins, the Insights workbook can compare report-only and enforced results side by side. It requires Microsoft Entra ID P1 and a Log Analytics workspace that's receiving sign-in logs[4].

