# The Tickets App (tk-multi-tickets)
[![stable](https://img.shields.io/badge/version-0.1.0-green.svg)](https://semver.org)</br>
*Developed at [Brand New School](https://brandnewschool.com).*

Tickets are a great way to track issues and development in your pipeline. However, for artists, creating tickets can be annoying and time consuming. tk-multi-tickets allows your artists to create tickets quickly in context, so they can focus on making art!

<img src="https://github.com/nybrandnewschool/tk-multi-tickets/blob/master/images/tickets_submitter.png"/>

# Features
- Create Tickets in context
- Attach multiple screengrabs
- Automatically create tickets from unhandled Python exceptions
    + Filter unhandled exceptions using includes and excludes patterns
    + Keep count of repeated unhandled exceptions
- Execute code before and after tickets are created using Hooks

# Unhandled Python Exceptions
Tickets can be configured to register a Python excepthook that will submit tickets to Shotgun when an unhandled exception occurs. You can optionally prompt artists with a dialog before the Ticket is submitted, allowing artists to provide additional details and attachments.

<img src="https://github.com/nybrandnewschool/tk-multi-tickets/blob/master/images/tickets_submitter_exception.png"/>

# Todo
- Document configuration
- Ticket Assignment
    + Add hook allowing developers to override how Tickets are assigned
    + Add default_assign_to setting
    + Add assigned_to field to Tickets Submitter dialog
- Ticket Templates
    + Allow configuring of templates for each Ticket type
    + Title and description should be customizable
