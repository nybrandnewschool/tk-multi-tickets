# Tickets (tk-multi-tickets)
[![stable](https://img.shields.io/badge/version-0.1.0-green.svg)](https://semver.org)
*Developed at [Brand New School](https://brandnewschool.com).*

Tickets are a great way to track issues and development in your pipeline. However, creating tickets can be annoying and time consuming. tk-multi-tickets allows your artists to create tickets right when they happen, then lets them get back to work!

<span>
<img src="https://github.com/danbradham/tk-multi-tickets/blob/master/images/tickets_submitter.png" width="50%"/><img src="https://github.com/danbradham/tk-multi-tickets/blob/master/images/tickets_submitter_exception.png" width="50%"/>
</span>

# Features
- Create Tickets in context
- Attach multiple screengrabs
- Automatically create tickets from unhandled Python exceptions
    + Filter unhandled exceptions using includes and excludes patterns
    + Keep count of repeated unhandled exceptions
- Execute code before and after tickets are created using Hooks


# Todo
- Document configuration
- Ticket Assignment
    + Add hook allowing developers to override how Tickets are assigned
    + Add default_assign_to setting
    + Add assigned_to field to Tickets Submitter dialog
