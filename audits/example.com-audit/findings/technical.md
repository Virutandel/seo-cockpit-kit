# Technical findings for example.com (DEMO DATA)

This file is fictional sample data that ships with SEO Cockpit so the dashboard has something to show. Delete the whole `audits/example.com-audit` folder once you have a real audit.

```json
{
 "categories": [
  {
   "name": "Technical SEO",
   "score": 82,
   "what_works": [
    "Demo: all sitemap URLs return 200",
    "Demo: HTTPS with a single canonical host"
   ],
   "findings": [
    {
     "title": "Demo: two redirect hops on the www host",
     "severity": "Medium",
     "description": "Fictional example. http://www.example.com goes through two redirects before the final page.",
     "recommendation": "Send every variant to the final HTTPS URL in one hop."
    },
    {
     "title": "Demo: 404 page returns status 200",
     "severity": "High",
     "description": "Fictional example. A made-up URL answers 200 with the not-found template.",
     "recommendation": "Return a real 404 status for unknown URLs."
    }
   ]
  },
  {
   "name": "On-Page SEO",
   "score": 74,
   "what_works": [
    "Demo: every page has one H1"
   ],
   "findings": [
    {
     "title": "Demo: 6 titles longer than 60 characters",
     "severity": "Low",
     "description": "Fictional example. Long titles are cut off in results.",
     "recommendation": "Shorten them and lead with the main phrase."
    }
   ]
  }
 ]
}
```
