    (function attachClickOutsideListener() {
        const doc = window.parent.document;
        
        // Prevent registering multiple duplicate listeners across Streamlit re-renders
        if (window.parent._sidebarOutsideClickListenerAttached) return;
        window.parent._sidebarOutsideClickListenerAttached = true;

        doc.addEventListener('click', function(e) {
            // Find sidebar element
            const sidebar = doc.querySelector('section[data-testid="stSidebar"]');
            if (!sidebar) return;

            // Check if sidebar is expanded
            const isExpanded = sidebar.getAttribute('aria-expanded') === 'true';
            if (!isExpanded) return;

            // Define buttons and regions
            const closeBtn = doc.querySelector('[data-testid="stSidebarCollapseButton"] button');
            const openNavBtn = doc.querySelector('button[data-testid="stHeaderNavButton"]');
            
            const clickedInsideSidebar = sidebar.contains(e.target);
            const clickedToggleBtn = (closeBtn && closeBtn.contains(e.target)) || 
                                     (openNavBtn && openNavBtn.contains(e.target));

            // If the user clicks outside the open sidebar and not on the toggle button
            if (!clickedInsideSidebar && !clickedToggleBtn) {
                if (closeBtn) {
                    closeBtn.click();
                } else if (openNavBtn) {
                    openNavBtn.click();
                }
            }
        }, true); // Use capture phase to catch clicks reliably
    })();
    
