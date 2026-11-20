# Performance findings for example.com (DEMO DATA)

This file is fictional sample data that ships with SEO Cockpit so the dashboard has something to show. Delete the whole `audits/example.com-audit` folder once you have a real audit.

```json
{
 "categories": [
  {
   "name": "Performance (CWV)",
   "score": 61,
   "what_works": [
    "Demo: CLS is 0 on the home page"
   ],
   "findings": [
    {
     "title": "Demo: hero image is 1.8 MB",
     "severity": "Critical",
     "description": "Fictional example. The largest element on mobile takes 4.9 s to paint.",
     "recommendation": "Serve a resized WebP hero and preload it."
    }
   ]
  },
  {
   "name": "Schema / Structured Data",
   "score": 80,
   "what_works": [
    "Demo: Organization and WebSite schema present"
   ],
   "findings": [
    {
     "title": "Demo: Article schema missing dateModified",
     "severity": "Low",
     "description": "Fictional example.",
     "recommendation": "Add dateModified next to datePublished."
    }
   ]
  },
  {
   "name": "AI Search Readiness",
   "score": 70,
   "what_works": [
    "Demo: AI crawlers are allowed in robots.txt"
   ],
   "findings": [
    {
     "title": "Demo: answers are buried below long intros",
     "severity": "Medium",
     "description": "Fictional example. The direct answer sits 400 words into most guides.",
     "recommendation": "Put a 40 to 60 word answer under each question heading."
    }
   ]
  },
  {
   "name": "Images",
   "score": 77,
   "what_works": [
    "Demo: every image has width and height"
   ],
   "findings": [
    {
     "title": "Demo: 14 images with empty alt text",
     "severity": "Low",
     "description": "Fictional example.",
     "recommendation": "Describe what each content image shows."
    }
   ]
  }
 ]
}
```
