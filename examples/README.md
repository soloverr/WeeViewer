# Demo Data Files

This directory contains sample XML and JSON files for demonstrating WeeViewer's capabilities.

## Files

### demo_data.xml
A comprehensive XML file showcasing a fictional company's organizational structure, including:
- Company information and contact details
- Multiple departments with nested employee data
- Employee skills and project assignments
- Product information with pricing plans
- Customer subscriptions and usage statistics
- Financial reports with revenue and expenses

**Features demonstrated:**
- Deeply nested XML structure (up to 7 levels)
- Various data types (strings, numbers, dates, boolean values)
- Repeating elements (employees, projects, customers)
- Complex attribute structures
- Mixed content elements

### demo_data.json
The equivalent JSON representation of the same company data structure.

**Features demonstrated:**
- Deeply nested JSON objects and arrays
- Various data types and structures
- Complex relationships between entities
- Mixed arrays and objects
- Large-scale data organization

## Usage

To use these demo files with WeeViewer:

1. Open WeeViewer application
2. Click "File" → "Open"
3. Navigate to this directory
4. Select either `demo_data.xml` or `demo_data.json`
5. Explore the data structure using the tree view
6. Try various features:
   - Navigate through the tree structure
   - Click on nodes to see their details
   - Use the search functionality
   - Add bookmarks to important nodes
   - Copy paths for data extraction
   - Export data in different formats

## Data Structure Overview

The demo data represents "TechInnovations Corporation" with the following hierarchy:

```
Company
├── Company Info
│   ├── Name, Founded Date
│   ├── Headquarters (Address, Contact)
└── Departments
    ├── Engineering (Employees, Projects, Skills)
    ├── Marketing (Employees, Projects, Skills)
    └── Human Resources (Employees, Projects, Skills)
├── Products
│   ├── TechAI Platform (Pricing, Release History)
│   └── DataSync Suite (Pricing, Release History)
├── Customers
│   ├── Subscriptions, Usage Statistics
│   └── Contact Information
└── Financial Reports
    ├── Revenue (by Product, by Region)
    ├── Expenses (by Category)
    └── Net Profit, Profit Margin
```

## Tips for Exploration

1. **Start with the top level**: Begin by exploring the root elements to understand the overall structure
2. **Use search**: Try searching for specific employees, projects, or customers
3. **Follow relationships**: Notice how departments contain employees, who work on projects
4. **Compare structures**: Open both XML and JSON versions to see how the same data is represented differently
5. **Test features**: Experiment with bookmarks, path copying, and export functions

## Customization

You can modify these files to create your own test data:
- Add new departments or employees
- Create different product configurations
- Add more customer scenarios
- Modify financial data for different periods

The files are intentionally designed to be complex enough to demonstrate WeeViewer's capabilities while remaining understandable and manageable.