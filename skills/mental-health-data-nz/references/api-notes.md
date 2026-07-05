# Mental Health Data NZ Source Notes

## ODMHAS regulatory reports

Primary source: Manatu Hauora / Ministry of Health mental health annual reports and publication pages.

Key report assets used by the CLI:

- 2023/24 regulatory report publication page: `https://www.health.govt.nz/publications/office-of-the-director-of-mental-health-and-addiction-services-regulatory-report-2023-to-2024`
- 2023/24 PDF: `https://www.health.govt.nz/system/files/2026-03/odmhas-regulatory-report-2023-24.pdf`
- 2023/24 DOCX: `https://www.health.govt.nz/system/files/2026-03/odmhas-regulatory-report-2023-24.docx`
- 2022/23 publication page: `https://www.health.govt.nz/publications/office-of-the-director-of-mental-health-and-addiction-services-regulatory-report-1-july-2022-to-30`
- 2022/23 PDF: `https://www.health.govt.nz/system/files/2025-02/Office-of-the-Director-of-Mental-Health-and-Addiction-Services-Regulatory-Report-2022-23.pdf`
- 2022/23 DOCX: `https://www.health.govt.nz/system/files/2025-02/Office-of-the-Director-of-Mental-Health-and-Addiction-Services-Regulatory-Report-2022-23.docx`
- 2021/22 PDF/DOCX: `https://www.health.govt.nz/system/files/2023-09/odmhas-regulatory-report-sep23.pdf` and `.docx`
- 2020/21 PDF/DOCX: `https://www.health.govt.nz/system/files/2022-09/odmhas-regulatory-report-sep22.pdf` and `.docx`
- 2020 calendar-year PDF/DOCX: `https://www.health.govt.nz/system/files/2021-11/office_of_the_director_of_mental_health_and_addiction_services_-_2020_regulatory_report_final_v2.pdf` and `.docx`

The Ministry's HTML publication and annual-report pages can return Cloudflare/CloudFront 403 to automated clients. Direct static report assets are often reachable. The CLI attempts live discovery, then falls back to the known report asset list and includes the discovery status.

## Seclusion and restraint extraction

The report DOCX files are ZIP archives containing WordprocessingML tables. The CLI extracts only tables that are present as structured DOCX table XML. It does not perform OCR or PDF chart digitisation.

Extracted where present:

- Appendix seclusion summary table, including/excluding prolonged or outlier cases
- Forensic mental health regional-service seclusion table
- Intellectual-disability seclusion tables by Act/region/ethnicity where present
- Adult inpatient admissions-with-seclusion percentage by district where present

Caveats:

- Adult inpatient district people/event rates are often charts, not DOCX tables. The CLI flags those as `chart_only_manual_extraction`.
- Terminology changes across reports: older reports may use DHB labels or "outliers"; newer reports use Health NZ districts and "prolonged periods of seclusion".
- PRIMHD source extracts behind dashboards or manual data tools are not treated as stable unauthenticated APIs.
- The skill reports values as source strings to avoid lossy conversion of rates, percentages, and hour-minute fields.

## MH&A KPI Programme

Primary source: `https://www.mhakpi.health.nz/`.

Public metadata pages:

- Indicators index: `https://www.mhakpi.health.nz/indicators/`
- Dashboards page: `https://www.mhakpi.health.nz/dashboards/`
- Indicator examples: wait times, whanau engagement, continuity of care, seclusion, 7-day follow-up, and 28-day readmission.

The public pages expose indicator descriptions, dashboard area links, and evidence-review resources. The data dashboards note registration/sign-in requirements. The CLI therefore treats KPI dashboard data as metadata-only unless a stable public export link appears in the HTML.

## Inpatient inspections and District Inspector sources

ODMHAS reports include a table for the number of section 95 inquiry reports and section 99 inspection reports received or completed by the Director. The CLI extracts that table from DOCX when available.

Related public sources:

- Mental health District Inspectors: `https://www.health.govt.nz/regulation-legislation/mental-health-and-addiction/mental-health-act/mental-health-district-inspectors`
- District Inspectors list: `https://www.health.govt.nz/regulation-legislation/mental-health-and-addiction/mental-health-act/mental-health-district-inspectors/district-inspectors-list`
- Section 99 Canterbury inspection source page: `https://www.health.govt.nz/regulation-legislation/mental-health-and-addiction/section-99-inspection-of-canterbury-mental-health-services`
- Section 99 Canterbury inspection report publication: `https://www.health.govt.nz/publications/section-99-inspection-into-canterbury-waitaha-adult-inpatient-and-associated-mental-health-services`
- Section 99 Waikato inspection report publication: `https://www.health.govt.nz/publications/section-99-inspection-of-waikato-district-health-board-mental-health-and-addiction-services`
- Section 95 Waikato inquiry source page: `https://www.health.govt.nz/regulation-legislation/mental-health-and-addiction/section-95-inquiry-into-the-treatment-of-a-patient-at-waikato-hospital`

The section 95/99 source pages and reports are not a normalised dataset. Treat them as publication discovery and provenance links, then extract report details manually unless an official DOCX/PDF table is available.
