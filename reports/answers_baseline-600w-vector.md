# Answers: baseline 600w vector

Chunks 600 words, retrieval `vector`, model `claude-haiku-5-5`, judge `claude-sonnet-5-5`.

| Metric | Value |
|---|---|
| Correct (of 41 answerable) | 85% |
| Correct or partial | 95% |
| Evidence passage retrieved (top 5) | 80% |
| Evidence passage cited (exact phrase) | 73% |
| Answers grounded in their citations | 77% |
| False "I don't know" | 5% |
| "I don't know" on unanswerable (6) | 100% |
| Avg tokens in / out | 7946 / 531 |
| Cost per 1,000 questions | $1.06 |
| Latency p50 / p95 | 3.2 s / 5.1 s |
| Avg retrieval / LLM time | 31 ms / 3.0 s |

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
| q10 | correct | - | How many words can we put on our custom banned password list? |
| q11 | correct | - | Can we switch off Microsoft's global banned password list? |
| q12 | correct | yes | How long can a custom security question for password reset be? |
| q13 | correct | yes | When will security questions stop working for self-service password reset? |
| q14 | correct | yes | I revoked a user's sessions. How long can the access token they already have keep working? |
| q15 | correct | yes | How many custom domain names can one tenant have? |
| q16 | correct | yes | Is there a limit to how many dynamic membership groups a tenant can have? |
| q17 | partial | - | I changed the rule of a dynamic group but its members haven't updated. How long can that take? |
| q18 | correct | yes | How many groups can a memberOf dynamic group rule reference? |
| q19 | correct | yes | We restricted what guest users can see in the directory. When does that take effect? |
| q20 | correct | yes | What counts as an inactive guest in the inactive guest report? |
| q21 | correct | yes | How far back can I see Conditional Access policy changes in the audit log? |
| q22 | correct | - | If a Conditional Access policy has several grant controls ticked, does the user have to satisfy all of them? |
| q23 | correct | yes | Does number matching work for Authenticator push notifications on an Apple Watch? |
| q24 | correct | - | What kind of hardware OATH tokens does Entra ID support? |
| q25 | correct | yes | Can B2B guest users sign in with SMS as their first factor? |
| q26 | correct | yes | How many people can use Windows Hello for Business on the same PC? |
| q27 | partial | yes | In combined MFA and SSPR registration, which methods are users shown by default? |
| q28 | correct | - | What happens to Conditional Access policies if Entra ID has an outage? |
| q29 | correct | yes | If I create a Conditional Access policy from a template, is it enforced right away? |
| q30 | correct | yes | How many authentication contexts can we define for Conditional Access? |
| q31 | correct | yes | What's the character limit for a filter for devices rule? |
| q32 | correct | yes | In a brand-new tenant, which methods are turned on in the Authentication methods policy? |
| q33 | correct | yes | Does SSPR password writeback work while staged rollout is enabled? |
| q34 | correct | yes | Can users see the custom security attributes on their own profile? |
| q35 | correct | - | A user restored Authenticator from a backup on a new phone and their work account says 'Sign in to add your account'. Is something wrong? |
| q36 | partial | - | Account recovery can't match a user against the identity verification provider. What should I check on the user object? |
| q37 | incorrect | - | Do users get the app name and location in their MFA prompt when signing in through the NPS extension? |
| q38 | correct | - | Can an admin look up a user's answers to their password reset security questions? |
| q39 | correct | yes | Without any Conditional Access policy, do users need MFA to register a passkey? |
| q40 | incorrect | - | Why can't I delete one of our named locations? |
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
**Judge:** The answer correctly states report-only mode, evaluated but not enforced, which matches the reference. But it omits the key limitation that report-only doesn't work for policies scoped to User Actions, which is an essential fact in the reference. It says 'most' policies, which hints at it but doesn't state the exception. So partial. Grounding: several claims are unsupported by the passages: the 'Report-only: Failure' and 'Not applied' outcome definitions, and the What If report listing applicable and non-applicable policies with reasons. These are not in the sources, so grounded is false.

> Yes. You can use report-only mode and the What If tool.
> 
> **Report-only mode:** Report-only mode is a policy state that lets administrators test most Conditional Access policies before enabling them.[1] During sign-in, the policy is evaluated but not enforced, and results are logged in the Conditional Access and Report-only tabs of the Sign-in log details.[1] Results are logged in the Conditional Access and Report-only tabs of the sign-in log details. Possible outcomes include "Report-only: Failure," meaning the conditions matched but a grant or session control wasn't met, and "Report-only: Not applied," meaning the policy's conditions weren't met. Customers with an Azure Monitor subscription can monitor the impact of their Conditional Access policies using the Conditional Access insights workbook.[1]
> 
> **What If tool:** This simulates a sign-in without waiting for real users to sign in. You can find it in the Microsoft Entra admin center > Entra ID > Conditional Access > Policies > What If.[2] Only policies that are enabled or in report-only mode are included in an evaluation run.[2] The report lists the policies that apply to the user and those that don't, along with the reason each one doesn't apply.
> 
> **Limitation:** The What If tool doesn't test for Conditional Access service dependencies.[2] Also, the What If API expects all sign-in parameters to be defined for the evaluation to provide the most accurate results.[3]

### q17: partial
**Q:** I changed the rule of a dynamic group but its members haven't updated. How long can that take?  
**Reference:** Depending on the size of the organization, populating can take up to 24 hours the first time or after a rule change.  
**Judge:** The reference says populating can take up to 24 hours the first time or after a rule change, depending on organization size. The answer says usually a few minutes, with large directories taking 30 minutes or longer, and never mentions the 24-hour upper bound. This misses the key fact and understates the time, so it is partial at best. It also says that the results don't state any duration beyond these general figures, which is misleading since passage 2 mentions 24 hours. On grounding: the 30-minute and few-minute claims, the error examples, whitespace trick, and alerts are all supported by the passages. However, the claim that statuses 'Evaluating, Processing, or Update complete' indicate normal progress, and 'Processing error means the rule couldn't be evaluated', do not appear in the passages. So the answer is not fully grounded.

> Usually a few minutes, but a large directory can take much longer. Small directories typically see dynamic membership group changes in less than a few minutes, while directories with many users can need 30 minutes or more to populate.[1]
> 
> To check progress, open the group's overview page. The rule processing status and the date of the last membership change appear there.[2] A status of Evaluating, Processing, or Update complete indicates normal progress. A status of Processing error means the rule couldn't be evaluated.
> 
> If the membership still doesn't change:
> 
> 1. **Check for a rule error.** If the rule isn't valid, the portal displays an explanation of why the rule couldn't be processed.[2] Common fixes are listed in the troubleshooting article, which shows examples such as "Error: Attribute not supported" and "Error: Operator isn't supported on attribute."[1]
> 2. **Look for alerts.** If an error occurs while processing the membership rule for a specific group, an alert appears at the top of the group's overview page.[2]
> 3. **Trigger reprocessing if needed.** The results say there's no on-demand option, but you can manually trigger reprocessing by updating the membership rule to add a whitespace at the end.[1]
> 
> The results don't say how long processing takes beyond these general figures, so if the status stays stuck, escalate it for further investigation.

### q27: partial
**Q:** In combined MFA and SSPR registration, which methods are users shown by default?  
**Reference:** The Microsoft Authenticator app and phone.  
**Judge:** The answer states that Microsoft Authenticator and phone are shown first in the example scenario, which matches the reference's key fact. It hedges by saying there is no general default list, but the source says 'shown by default' for that scenario. The key facts are present and not contradicted, though the hedging is somewhat stronger than the reference. Grounding: claims are supported by source 1 and 2. The claim that the flowchart isn't included in the excerpts is a statement about absence, not contradicted by the passages. Overall the answer is mostly correct, but the hedge about 'no general default list' makes it somewhat less definite than the reference; I judge it partial.

> The results give only one example of default methods. In a scenario where a user is enabled for SSPR. The SSPR policy requires two methods to reset and is enabled Microsoft Authenticator app, email, and phone.[1] In that case, the registration prompt presents Microsoft Authenticator and phone first, and the user can choose email instead of one of them.
> 
> The results don't give a general default list. Which methods appear depends on the tenant's Authentication methods policy, as the list of available methods is determined by the Authentication methods policy for the tenant.[2] The flowchart that shows which methods are displayed during sign-in registration isn't included in the excerpts.

### q36: partial
**Q:** Account recovery can't match a user against the identity verification provider. What should I check on the user object?  
**Reference:** That the First Name and Last Name properties aren't blank; if either is blank, account recovery can't match the provider's claims.  
**Judge:** The reference's key fact: check that First Name and Last Name properties aren't blank. The answer identifies First name and Last name as the properties to check, but frames it as mismatch with the ID rather than blank values, never mentioning blank. So it misses the essential 'not blank' point, though it doesn't contradict it. Partial. Grounding: claims about name matching, exact/relaxed, mismatches, admin fix, group membership are supported by passages. The statement 'set on the identity verification profile, not the user' is an inference not explicitly in passages (passage says admins can configure match confidence level). The closing sentence about custom authentication extension is not supported by the passages. So not fully grounded.

> The user object's **First name and Last name** properties are the main thing to check. By default, account recovery matches identity claims from the verification provider against the user's First name and Last name properties in Microsoft Entra ID.[1] A mismatch can block ownership validation. Differences such as "John" versus "Jonathan", or complex surnames, might cause these issues.[2]
> 
> Suggested checks:
> 
> 1. **Compare the name fields to the government ID.** Confirm the first and last names on the user object match the ID the user presented.
> 2. **Correct any mismatch.** Admins can resolve this during the preview by updating profile information.[2]
> 3. **Review the match setting on the profile.** Exact — Claims must match exactly. Relaxed — Allows minor variations in name matching.[1] This is set on the identity verification profile, not the user, so it's a second place to look if names are close but not identical.
> 4. **Confirm the user is in the profile's group.** If they aren't part of the selected group, then they won't be offered the recovery task during login.[2]
> 
> The results don't cover whether the user's other profile attributes affect matching beyond name fields, unless a custom authentication extension is configured.

### q37: incorrect
**Q:** Do users get the app name and location in their MFA prompt when signing in through the NPS extension?  
**Reference:** No, additional context isn't supported for the NPS extension or AD FS.  
**Judge:** said it doesn't know (false refusal)

> I don't know. The results don't say whether the NPS extension sign-in prompt shows the application name or location. They describe the Authenticator push prompt in general, and they mention NPS only in the context of sign-in logs.
> 
> - For Authenticator approval requests, the app's name and an IP-based location are the details an approver can see when a user receives a passwordless phone sign-in or multifactor authentication (MFA) push notification in Authenticator[1]. This article doesn't say whether that applies to requests that come through NPS.
> - For NPS, the results cover logging rather than the prompt. Organizations that run the latest version of NPS extension or use Microsoft Entra Connect Health will have location IP address in events.[2]
> - Admins should also confirm targeting. Only users who are enabled for Authenticator under `includeTargets` see the application name or geographic location.[1]
> 
> To confirm the NPS prompt behavior, check Microsoft's documentation for the NPS extension or test with a user in scope.

### q40: incorrect
**Q:** Why can't I delete one of our named locations?  
**Reference:** Locations marked as trusted can't be deleted until the trusted designation is removed.  
**Judge:** said it doesn't know (false refusal)

> I don't know. The search results only cover deleting custom domain names, Microsoft Entra tenants, and self-service sign-up products, and they don't mention named locations or Conditional Access.

