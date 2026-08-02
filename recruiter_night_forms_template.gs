/**
 * =============================================================================
 * Recruiter Night — Google Forms builder (template)
 * =============================================================================
 * Builds three native Google Forms for a pre-career-fair matching event:
 * employer registration, student registration, and a later "must-meet picks"
 * form once your recruiter roster is locked.
 *
 * This is a template. Fill in CONFIG below with your own organization's
 * details, then run it. Everything else (question wording, logic, layout)
 * works as-is, but read the "CUSTOMIZE THIS" comments throughout, especially
 * MAJORS and INDUSTRIES, which are just one school's example taxonomy.
 *
 * HOW TO RUN THIS
 *   1. Fill in the CONFIG block right below this comment.
 *   2. Go to script.google.com -> New project.
 *   3. Delete the placeholder code, paste this whole file in.
 *   4. Pick createAllForms from the function dropdown at the top, click Run.
 *   5. First run will ask you to authorize — approve it (it's your own script,
 *      running under your own account, touching only Forms it creates).
 *   6. View > Logs (or Execution log) to get the two form URLs.
 *   7. Form 3 (must-meet picks) is separate — see the bottom of this file.
 *
 * DESIGN CHOICES BAKED INTO THIS SCRIPT, AND WHY
 *   1. No file-upload question anywhere. Google Forms forces every respondent
 *      to sign in with a Google account the moment a form contains a file
 *      upload field, with no setting to turn that off. That would block
 *      external recruiters who don't have an account at your school. The
 *      company-logo ask is a plain "paste a link" text field instead.
 *   2. No ranking question. Google Forms has no native ranking/drag-to-order
 *      question type. The usual workaround (a multiple-choice grid) exports
 *      as one column per item and is a confusing UI. Since the matching
 *      engine only ever reads a student's top 2 industry picks anyway, this
 *      just asks for those two directly as separate dropdowns.
 *   3. Major is a dropdown with "Other (please specify below)" plus a
 *      follow-up text field, since Google Forms dropdowns don't support an
 *      inline "Other" the way multiple-choice questions do.
 *
 * WHAT THIS SCRIPT DID NOT VERIFY FOR YOU
 *   The methods used below are standard, documented Google Apps Script
 *   FormApp calls, but this template hasn't been run in every Google
 *   Workspace configuration. Run it once and check the Logs before relying
 *   on it for a real event.
 *
 * ONE THING TO CHECK MANUALLY AFTER RUNNING
 *   If your Google account is a managed school Workspace account, newly
 *   created forms sometimes default to "Restrict to users in [organization]."
 *   That setting isn't exposed through Apps Script, so open the recruiter
 *   form -> Settings -> General and confirm that toggle is OFF. It must stay
 *   off, or external recruiters without an account at your school can't
 *   respond. The student form can go either way, your call.
 *
 * EXPORTING RESPONSES FOR THE PYTHON PIPELINE
 *   Each form's Responses tab has a green Sheets icon — click it once to
 *   link a response spreadsheet. When you're ready to run forms_to_csv.py,
 *   open that Sheet and use File > Download > Microsoft Excel (.xlsx).
 * =============================================================================
 */

// ---------------------------------------------------------------------------
// CONFIG — fill in your own details before running anything.
// ---------------------------------------------------------------------------

var CONFIG = {
  ORG_NAME: 'Your Organization',                 // the group running the event
  SCHOOL_NAME: 'Your University',
  SCHOOL_EMAIL_DOMAIN: 'youruniversity.edu',      // used in helper text only
  EVENT_NAME: 'Recruiter Night',
  EVENT_DATE_TEXT: 'TBD',                         // e.g. 'Tuesday, September 15'
  EVENT_TIME_TEXT: 'TBD',                         // e.g. '5:30–8:00 PM'
  CAREER_FAIR_DATE_TEXT: 'TBD',                   // e.g. 'Tuesday, September 22'
  CATERER_NAME: 'your caterer',
  CO_SPONSOR_ORG: '[your co-sponsoring organization]'  // or delete the checkbox option below
};

// ---------------------------------------------------------------------------
// SHARED DATA — CUSTOMIZE THIS. These are one school's example majors and
// industry groupings (originally Missouri S&T's). Replace both lists with
// whatever your own institution and target industries actually look like.
// Keep forms_to_csv.py's MAJORS list and canon_industry() buckets in sync
// with whatever you put here, or the converter won't recognize the answers.
// ---------------------------------------------------------------------------

var MAJORS = [
  'Aerospace Engineering', 'Applied Mathematics', 'Architectural Engineering',
  'Biological Sciences', 'Business & Management Systems', 'Ceramic Engineering',
  'Chemical Engineering', 'Chemistry', 'Civil Engineering', 'Computer Engineering',
  'Computer Science', 'Electrical Engineering', 'Engineering Management',
  'Environmental Engineering', 'Environmental Science', 'Geological Engineering',
  'Geology', 'History', 'Information Science & Technology', 'Mechanical Engineering',
  'Metallurgical Engineering', 'Mining Engineering', 'Nuclear Engineering',
  'Petroleum Engineering', 'Physics', 'Psychology', 'Technical Communication'
];

var INDUSTRIES = [
  'Civil, Construction & Infrastructure', 'Manufacturing & Industrial',
  'Mechanical, Aerospace & Defense', 'Materials, Mining & Chemical',
  'Energy, Power & Utilities', 'Electrical, Controls & Automation',
  'Software & IT', 'Data, Systems & Analytics', 'Business, Finance & Consulting'
];

// ---------------------------------------------------------------------------
// ENTRY POINT — run this one first
// ---------------------------------------------------------------------------

function createAllForms() {
  var recruiterForm = createRecruiterForm();
  var studentForm = createStudentRegistrationForm();

  Logger.log('RECRUITER FORM');
  Logger.log('  fill out:  ' + recruiterForm.getPublishedUrl());
  Logger.log('  edit:      ' + recruiterForm.getEditUrl());
  Logger.log('');
  Logger.log('STUDENT REGISTRATION FORM');
  Logger.log('  fill out:  ' + studentForm.getPublishedUrl());
  Logger.log('  edit:      ' + studentForm.getEditUrl());
  Logger.log('');
  Logger.log('Form 3 (must-meet picks) is separate. Once your recruiter roster');
  Logger.log('is locked, fill in the COMPANIES_PLACEHOLDER array near the bottom');
  Logger.log('of this file with your real roster, then run createMustMeetForm().');
}

// ---------------------------------------------------------------------------
// FORM 1 — RECRUITER INTAKE
// ---------------------------------------------------------------------------

function createRecruiterForm() {
  var form = FormApp.create(
    `${CONFIG.EVENT_NAME} at ${CONFIG.SCHOOL_NAME} — Employer Registration`);

  form.setDescription(
    `Thank you for joining us ${CONFIG.EVENT_DATE_TEXT} — ahead of the ` +
    `${CONFIG.SCHOOL_NAME} career fair. This is a free, seated, dinner-format event. ` +
    "We match you in advance with students who fit what you're hiring for, so you're " +
    "not fielding hundreds of unfiltered résumés.\n\n" +
    'This form takes about 4 minutes. Everything here feeds the matching system, so please ' +
    'be specific — the more precise your answers, the better your table traffic.'
  );
  form.setConfirmationMessage(
    "You're confirmed. We'll send your matched student roster and table assignment " +
    'before the event.'
  );
  form.setCollectEmail(false);            // collected ourselves in Q3
  form.setLimitOneResponsePerUser(false); // MUST stay off. This forces Google sign-in,
                                           // which would block every external recruiter.
                                           // Duplicate submissions are already merged in
                                           // forms_to_csv.py by matching the Q3 email.

  // --- Section 1: Contact & Logistics --------------------------------------
  form.addSectionHeaderItem().setTitle('Contact & Logistics');

  form.addTextItem()
    .setTitle('Company / organization name')
    .setHelpText("Exactly as you'd like it printed on your table tent and signage.")
    .setRequired(true);

  form.addTextItem()
    .setTitle('Primary contact name')
    .setRequired(true);

  form.addTextItem()
    .setTitle('Primary contact email')
    .setValidation(FormApp.createTextValidation().requireTextIsEmail().build())
    .setRequired(true);

  form.addTextItem()
    .setTitle('Mobile number for day-of coordination')
    .setRequired(false);

  form.addMultipleChoiceItem()
    .setTitle('How many recruiters will attend from your company?')
    .setChoiceValues(['1', '2', '3', '4 or more'])
    .setHelpText(
      'This is the single most important logistics question. The matching system weights ' +
      'your student load by rep count — two reps means you meet roughly twice as many ' +
      'students. Getting this wrong is the #1 cause of a lopsided room.'
    )
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle(`Will you also be attending the ${CONFIG.CAREER_FAIR_DATE_TEXT} career fair?`)
    .setChoiceValues([
      "Yes, we're registered for the career fair",
      "No, we're not attending the career fair this year",
      'Undecided'
    ])
    .setHelpText('No wrong answer — this just helps us plan parking and setup.')
    .setRequired(true);

  // --- Section 2: What You're Hiring For -----------------------------------
  form.addSectionHeaderItem().setTitle("What You're Hiring For");

  form.addCheckboxItem()
    .setTitle('What roles are you recruiting for?')
    .setChoiceValues([
      'Summer internship',
      'Co-op (semester-long)',
      'Full-time',
      'Rotational / leadership development program'
    ])
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('Do you have full-time openings, or internships and co-ops only?')
    .setChoiceValues([
      'We have full-time openings for graduating seniors',
      'Internships and co-ops only right now',
      'Both full-time and internships/co-ops'
    ])
    .setHelpText(
      'This question lets the system steer graduating seniors toward you if you have ' +
      'full-time openings, and steer them elsewhere if you do not.'
    )
    .setRequired(true);

  form.addCheckboxItem()
    .setTitle('Which majors are you most interested in?')
    .setChoiceValues(MAJORS.concat(['Open to any major']))
    .setHelpText(
      'Select generously. Selecting adjacent majors meaningfully increases your table ' +
      'traffic, and students cross disciplines more than you would expect.'
    )
    .setRequired(true);

  form.addCheckboxItem()
    .setTitle('Which class years are you open to meeting?')
    .setChoiceValues(['Freshman', 'Sophomore', 'Junior', 'Senior', 'Graduate student'])
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('If we have strong sophomores in your target majors, would you be willing to meet a few?')
    .setChoiceValues([
      'Yes — happy to meet promising underclassmen',
      "Only if they're exceptional",
      'No, we only recruit juniors and seniors'
    ])
    .setHelpText(
      'Most schools have more underclassmen than upperclassmen, but most employers ' +
      'default to "junior/senior." Saying yes here meaningfully widens your pool, and ' +
      'sophomores are your cheapest pipeline, they can intern twice before they graduate.'
    )
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('Which industry best describes your work?')
    .setChoiceValues(INDUSTRIES)
    .setHelpText(
      'This sets your table color and where you sit in the room. Tables are grouped so ' +
      'related industries sit near each other.'
    )
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('Can you sponsor work visas (CPT / OPT / H-1B) for any of your openings?')
    .setChoiceValues([
      'Yes, for at least some roles',
      'No, all roles require permanent US work authorization',
      'Case-by-case / not sure yet'
    ])
    .setHelpText(
      'This is a hard filter, not a preference. Nothing wastes a conversation faster than ' +
      'discovering at minute six that a student is not eligible. "Case-by-case" is treated ' +
      'as yes.'
    )
    .setRequired(true);

  form.addTextItem()
    .setTitle('Primary work locations for these roles')
    .setHelpText('City, State. List up to three, comma-separated.')
    .setRequired(true);

  // --- Section 3: Event Experience (optional) ------------------------------
  form.addSectionHeaderItem().setTitle('Event Experience (optional but appreciated)');

  form.addTextItem()
    .setTitle('Any dietary restrictions for your team?')
    .setHelpText('Dinner is catered. We\'ll accommodate.')
    .setRequired(false);

  form.addMultipleChoiceItem()
    .setTitle('Would you like a reserved parking spot near the venue?')
    .setChoiceValues(['Yes please', 'Not needed'])
    .setRequired(false);

  // See header note #1 — native file upload would force every respondent to
  // sign in to Google, which breaks "anyone can respond." Link field instead.
  form.addTextItem()
    .setTitle('Link to your company logo for table signage (optional)')
    .setHelpText('Paste a shareable link — Drive, Dropbox, your site, anywhere we can grab it from.')
    .setRequired(false);

  form.addParagraphTextItem()
    .setTitle('Anything else we should know?')
    .setRequired(false);

  return form;
}

// ---------------------------------------------------------------------------
// FORM 2 — STUDENT REGISTRATION
// ---------------------------------------------------------------------------

function createStudentRegistrationForm() {
  var form = FormApp.create(`${CONFIG.EVENT_NAME} — Student Registration`);

  form.setDescription(
    `${CONFIG.EVENT_DATE_TEXT} · ${CONFIG.EVENT_TIME_TEXT} · ` +
    `Free dinner (${CONFIG.CATERER_NAME}) · Business casual\n\n` +
    'Meet recruiters ahead of the career fair — including companies that are not ' +
    "attending the fair at all. You'll get a personalized card listing the companies " +
    'matched to your major, year, and interests. No standing in line, no wandering. Dinner ' +
    'first, everyone eats together, then you meet your matches.\n\n' +
    'Space is limited and we expect to fill up. Registering does not guarantee a spot — ' +
    "we'll confirm by email. Takes about 3 minutes."
  );
  form.setConfirmationMessage(
    "You're registered. Watch your email for a short follow-up to pick your must-meet " +
    "companies, plus your personalized card before the event."
  );
  form.setCollectEmail(false); // collected ourselves in Q2, your school address

  // --- Section 1: About You -------------------------------------------------
  form.addSectionHeaderItem().setTitle('About You');

  form.addTextItem().setTitle('Full name').setRequired(true);

  form.addTextItem()
    .setTitle(`${CONFIG.SCHOOL_NAME} email`)
    .setHelpText(`Should end in @${CONFIG.SCHOOL_EMAIL_DOMAIN}`)
    .setValidation(FormApp.createTextValidation().requireTextIsEmail().build())
    .setRequired(true);

  // See header note #3 — dropdowns can't natively do inline "Other," so it's
  // a choice plus a follow-up text field.
  var majorItem = form.addListItem()
    .setTitle('Major')
    .setHelpText("If you're double-majoring, pick the one you most want to recruit in.")
    .setRequired(true);
  majorItem.setChoiceValues(MAJORS.concat(['Other (please specify below)']));

  form.addTextItem()
    .setTitle('If you selected Other above, what is your major?')
    .setRequired(false);

  form.addTextItem()
    .setTitle('Second major or minor')
    .setHelpText("We'll use this to widen your matches if it helps.")
    .setRequired(false);

  form.addMultipleChoiceItem()
    .setTitle('Class standing this fall')
    .setChoiceValues(['Freshman', 'Sophomore', 'Junior', 'Senior', 'Graduate student'])
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('Expected graduation')
    .setChoiceValues(['December 2026', 'May 2027', 'December 2027', 'May 2028', 'May 2029 or later'])
    .setHelpText('CUSTOMIZE THIS — update the years to match your own event\'s timeframe.')
    .setRequired(true);

  form.addCheckboxItem()
    .setTitle('What are you looking for?')
    .setChoiceValues([
      'Summer internship',
      'Co-op (semester-long)',
      'Full-time job after graduation',
      'Just exploring / building my network'
    ])
    .setHelpText(
      '"Just exploring" is a real answer and will not hurt your matches — it tells the ' +
      'system to weight fit by major rather than by role type. Freshmen especially should ' +
      'feel free to pick it.'
    )
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('Do you now or will you in the future require visa sponsorship to work in the US?')
    .setChoiceValues([
      'No — I have permanent US work authorization',
      'Yes — I need or will need sponsorship'
    ])
    .setHelpText(
      'This is a hard filter. We will never match you with a company that cannot hire you, ' +
      'so you do not waste a conversation finding that out in person.'
    )
    .setRequired(true);

  // --- Section 2: What You Want ---------------------------------------------
  form.addSectionHeaderItem().setTitle('What You Want (this drives your matches)');

  // See header note #2 — two single picks instead of a 9-way ranking. The
  // matching engine only ever reads your top 2 industries anyway.
  form.addListItem()
    .setTitle('First choice: which industry interests you most?')
    .setChoiceValues(INDUSTRIES)
    .setHelpText(
      'Be honest rather than strategic — this is what the system uses to find you ' +
      'companies you will actually want to talk to.'
    )
    .setRequired(true);

  form.addListItem()
    .setTitle('Second choice: which industry interests you next most?')
    .setChoiceValues(INDUSTRIES)
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('Where do you want to work?')
    .setChoiceValues([`${CONFIG.SCHOOL_NAME}'s home state`, 'Regionally', 'Anywhere in the US'])
    .setHelpText('CUSTOMIZE THIS — swap in your own region\'s framing if this doesn\'t fit.')
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('What size company appeals to you?')
    .setChoiceValues([
      'Small (under 100 people) — more responsibility early',
      'Mid-size (100–1,000)',
      'Large (1,000+) — structured programs, big name',
      'No preference'
    ])
    .setHelpText(
      'Many of our guests are smaller regional firms who do not attend the career fair. ' +
      'If you want that, we will point you at them.'
    )
    .setRequired(true);

  // --- Section 3: Your Dream List --------------------------------------------
  form.addSectionHeaderItem().setTitle('Your Dream List');

  form.addTextItem()
    .setTitle("Name up to 3 companies you'd most like to meet — any company at all")
    .setHelpText(
      'Separate with commas. These do NOT have to be companies attending. We are still ' +
      'sending invitations, and we genuinely use this list to decide who to chase. If a ' +
      'company you name ends up coming, you get an automatic guaranteed meeting with them.'
    )
    .setRequired(false);

  form.addTextItem()
    .setTitle('Is there a company already on our confirmed list you especially want to meet?')
    .setHelpText(
      "Leave blank if you haven't seen the list yet, we'll follow up with a short form to " +
      "pick your must-meets closer to the event. You're not missing out by skipping this."
    )
    .setRequired(false);

  // --- Section 4: Logistics ---------------------------------------------------
  form.addSectionHeaderItem().setTitle('Logistics');

  // Replace or delete the co-sponsor option below once you know your real one.
  form.addCheckboxItem()
    .setTitle('Are you a member of any of the following?')
    .setChoiceValues([
      CONFIG.ORG_NAME,
      CONFIG.CO_SPONSOR_ORG,
      'Neither — I saw this through campus'
    ])
    .setHelpText('This event is open to all students. We ask only for our event reporting.')
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('Do you consent to photos being taken at the event?')
    .setChoiceValues(['Yes', "No — please don't photograph me"])
    .setHelpText('CUSTOMIZE THIS — delete if your event has no photo/funding reporting requirement.')
    .setRequired(true);

  return form;
}

// ---------------------------------------------------------------------------
// FORM 3 — MUST-MEET PICKS
// Run this by itself once your recruiter roster is locked.
// Fill in COMPANIES_PLACEHOLDER first — it currently has example rows only.
// ---------------------------------------------------------------------------

// Format each entry as: "Company — Industry — hiring: Majors — roles: X"
// Group by industry so it reads cleanly as a checkbox list.
var COMPANIES_PLACEHOLDER = [
  'Example Manufacturing Co. — Manufacturing & Industrial — hiring: Mechanical, Industrial — roles: Internship, Co-op',
  'Example Software Inc. — Software & IT — hiring: Computer Science, Computer Engineering — roles: Internship, Full-Time'
  // ... add the rest of your confirmed roster here
];

function createMustMeetForm() {
  var companies = COMPANIES_PLACEHOLDER; // <-- swap this for your real, locked roster

  if (companies.length < 3) {
    throw new Error(
      'COMPANIES_PLACEHOLDER still has only example rows. Fill in your real, locked ' +
      'roster before running createMustMeetForm().'
    );
  }

  var form = FormApp.create(`${CONFIG.EVENT_NAME} — Pick Your Must-Meets`);
  form.setDescription(
    "Our recruiter list is locked. Pick the two companies you most want to meet and we'll " +
    'guarantee you a seat with them, regardless of what the matching algorithm says. ' +
    'Everything else on your card gets matched to your major and interests automatically. ' +
    'This takes 30 seconds. If you skip it, we will pick good ones for you based on what ' +
    'you told us when you registered — you will not lose anything.'
  );
  form.setCollectEmail(false);

  form.addTextItem()
    .setTitle(`Your ${CONFIG.SCHOOL_NAME} email`)
    .setHelpText('Must match the one you registered with so we can link your responses.')
    .setValidation(FormApp.createTextValidation().requireTextIsEmail().build())
    .setRequired(true);

  var pickItem = form.addCheckboxItem()
    .setTitle('Pick up to 2 companies you most want to meet')
    .setHelpText('Listed by industry. Full details on each company are in the email.')
    .setChoiceValues(companies)
    .setRequired(true);
  pickItem.setValidation(FormApp.createCheckboxValidation().requireSelectAtMost(2).build());

  // This question's branching is wired below, after its target page exists.
  var changeItem = form.addMultipleChoiceItem().setTitle('Anything change since you registered?');

  // Only reached if they say something changed. Last section, so it submits
  // automatically once filled in — no extra navigation needed.
  var followUpPage = form.addPageBreakItem().setTitle('Tell us what changed');
  form.addParagraphTextItem().setTitle('What changed?').setRequired(false);

  changeItem.setChoices([
    changeItem.createChoice('Nope, all the same', FormApp.PageNavigationType.SUBMIT),
    changeItem.createChoice('Yes — my class year or major changed', followUpPage)
  ]);

  Logger.log('MUST-MEET PICKS FORM');
  Logger.log('  fill out:  ' + form.getPublishedUrl());
  Logger.log('  edit:      ' + form.getEditUrl());

  return form;
}
