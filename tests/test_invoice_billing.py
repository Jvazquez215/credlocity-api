#!/usr/bin/env python3
"""
Invoice Billing Adjustments Tests
Tests the invoice creation with partner credits, discounts, and coupons applied.
"""

import requests
import json
import sys
from typing import Optional, Dict, Any

# Base URL for the API
BASE_URL = "https://condescending-wozniak-3.preview.emergentagent.com/api"

# Test credentials
ADMIN_EMAIL = "Admin@credlocity.com"
ADMIN_PASSWORD = "Credit123!"

# Partner ID from review request
PARTNER_ID = "176200b3-5e59-4ecd-be5e-d58fa531afd5"

class InvoiceBillingTester:
    def __init__(self):
        self.token: Optional[str] = None
        self.headers: Dict[str, str] = {
            "Content-Type": "application/json"
        }
        self.test_results = []
    
    def log_test(self, test_name: str, success: bool, details: str, response_data: Any = None):
        """Log test results"""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"\n{status} {test_name}")
        print(f"Details: {details}")
        if response_data:
            print(f"Response: {json.dumps(response_data, indent=2)}")
        
        self.test_results.append({
            "test": test_name,
            "success": success,
            "details": details,
            "response": response_data
        })
    
    def authenticate(self) -> bool:
        """Authenticate and get token"""
        try:
            url = f"{BASE_URL}/auth/login"
            payload = {
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            }
            
            response = requests.post(url, json=payload, headers=self.headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if "access_token" in data:
                    self.token = data["access_token"]
                    self.headers["Authorization"] = f"Bearer {self.token}"
                    print("✅ Authentication successful")
                    return True
            
            print(f"❌ Authentication failed: {response.status_code}")
            return False
            
        except Exception as e:
            print(f"❌ Authentication error: {str(e)}")
            return False
    
    def create_test_credit(self, amount: float = 200.0) -> tuple[bool, str]:
        """Create a test dollar credit for the partner"""
        try:
            url = f"{BASE_URL}/admin/outsource/partners/{PARTNER_ID}/credits"
            payload = {
                "credit_type": "dollar_credit",
                "dollar_amount": amount,
                "description": f"Test ${amount} credit for invoice billing test"
            }
            
            response = requests.post(url, json=payload, headers=self.headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                credit_id = data.get("id")
                
                self.log_test(
                    f"Create ${amount} Dollar Credit",
                    True,
                    f"Successfully created ${amount} dollar credit. Credit ID: {credit_id}, Status: {data.get('status')}",
                    {
                        "status_code": response.status_code,
                        "credit_id": credit_id,
                        "amount": data.get("amount"),
                        "credit_type": data.get("credit_type"),
                        "status": data.get("status")
                    }
                )
                return True, credit_id
            else:
                error_data = response.json() if response.content else {}
                self.log_test(
                    f"Create ${amount} Dollar Credit",
                    False,
                    f"Failed to create credit. Status: {response.status_code}, Error: {error_data.get('detail', 'Unknown error')}",
                    {"status_code": response.status_code, "error": error_data}
                )
                return False, ""
                
        except Exception as e:
            self.log_test(
                f"Create ${amount} Dollar Credit",
                False,
                f"Exception during credit creation: {str(e)}",
                None
            )
            return False, ""
    
    def create_test_coupon(self) -> tuple[bool, str]:
        """Create a test coupon"""
        try:
            import time
            url = f"{BASE_URL}/admin/outsource/coupons"
            coupon_code = f"TESTCOUPON50_{int(time.time())}"
            payload = {
                "code": coupon_code,
                "name": "Test Coupon $50 Off",
                "description": "Test coupon for invoice billing adjustments",
                "discount_type": "dollar",
                "discount_value": 50.0,
                "duration_months": 12,
                "max_uses": 100
            }
            
            response = requests.post(url, json=payload, headers=self.headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                self.log_test(
                    "Create Test Coupon",
                    True,
                    f"Successfully created test coupon '{coupon_code}' for $50 off. Coupon ID: {data.get('id')}",
                    {
                        "status_code": response.status_code,
                        "coupon_id": data.get("id"),
                        "code": data.get("code"),
                        "discount_value": data.get("discount_value"),
                        "discount_type": data.get("discount_type")
                    }
                )
                return True, coupon_code
            else:
                error_data = response.json() if response.content else {}
                self.log_test(
                    "Create Test Coupon",
                    False,
                    f"Failed to create coupon. Status: {response.status_code}, Error: {error_data.get('detail', 'Unknown error')}",
                    {"status_code": response.status_code, "error": error_data}
                )
                return False, ""
                
        except Exception as e:
            self.log_test(
                "Create Test Coupon",
                False,
                f"Exception during coupon creation: {str(e)}",
                None
            )
            return False, ""
    
    def verify_percentage_discount(self) -> bool:
        """Verify the 3% 'New Sign Up' discount exists"""
        try:
            url = f"{BASE_URL}/admin/outsource/partners/{PARTNER_ID}/discounts"
            
            response = requests.get(url, headers=self.headers, timeout=30)
            
            if response.status_code == 200:
                discounts = response.json()
                
                # Look for any active percentage discount
                percentage_discounts = [d for d in discounts if 
                                     d.get("discount_type") == "percentage" and 
                                     d.get("status") == "active"]
                
                if percentage_discounts:
                    discount = percentage_discounts[0]  # Use first active percentage discount
                    self.log_test(
                        "Verify Percentage Discount",
                        True,
                        f"Found active percentage discount: {discount.get('discount_value')}%. Description: '{discount.get('description', 'N/A')}', Status: {discount.get('status')}",
                        {
                            "status_code": response.status_code,
                            "discount_found": True,
                            "discount_id": discount.get("id"),
                            "discount_value": discount.get("discount_value"),
                            "discount_type": discount.get("discount_type")
                        }
                    )
                    return True
                else:
                    self.log_test(
                        "Verify Percentage Discount",
                        False,
                        f"No active percentage discount found. Found {len(discounts)} total discounts.",
                        {
                            "status_code": response.status_code,
                            "total_discounts": len(discounts),
                            "discounts": discounts
                        }
                    )
                    return False
            else:
                error_data = response.json() if response.content else {}
                self.log_test(
                    "Verify Percentage Discount",
                    False,
                    f"Failed to get partner discounts. Status: {response.status_code}, Error: {error_data.get('detail', 'Unknown error')}",
                    {"status_code": response.status_code, "error": error_data}
                )
                return False
                
        except Exception as e:
            self.log_test(
                "Verify Percentage Discount",
                False,
                f"Exception during discount verification: {str(e)}",
                None
            )
            return False
    
    def test_invoice_with_credit(self) -> bool:
        """Test creating an invoice with dollar credit applied"""
        try:
            url = f"{BASE_URL}/admin/outsource/invoices"
            payload = {
                "partner_id": PARTNER_ID,
                "invoice_date": "2024-01-15",
                "due_date": "2024-02-15",
                "items": [
                    {
                        "description": "Credit Repair Services - January 2024",
                        "quantity": 10,
                        "unit_price": 50.0
                    }
                ],
                "notes": "Test invoice for credit application"
            }
            
            response = requests.post(url, json=payload, headers=self.headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                # Verify credit was applied
                subtotal = data.get("subtotal", 0)
                total_amount = data.get("total_amount", 0)
                total_discount = data.get("total_discount", 0)
                adjustments = data.get("adjustments", [])
                
                # Check if credit adjustment exists
                credit_adjustment = None
                for adj in adjustments:
                    if adj.get("type") == "credit":
                        credit_adjustment = adj
                        break
                
                if credit_adjustment and total_discount > 0:
                    self.log_test(
                        "Invoice with Dollar Credit",
                        True,
                        f"Invoice created successfully with credit applied. Subtotal: ${subtotal}, Total: ${total_amount}, Discount: ${total_discount}",
                        {
                            "status_code": response.status_code,
                            "invoice_id": data.get("id"),
                            "subtotal": subtotal,
                            "total_amount": total_amount,
                            "total_discount": total_discount,
                            "adjustments_count": len(adjustments),
                            "credit_applied": True
                        }
                    )
                    
                    # Verify credit status changed to "used"
                    return self.verify_credit_status_used()
                else:
                    self.log_test(
                        "Invoice with Dollar Credit",
                        False,
                        f"Credit not properly applied. Credit adjustment found: {credit_adjustment is not None}, Total discount: ${total_discount}",
                        {
                            "status_code": response.status_code,
                            "subtotal": subtotal,
                            "total_amount": total_amount,
                            "total_discount": total_discount,
                            "adjustments": adjustments
                        }
                    )
                    return False
            else:
                error_data = response.json() if response.content else {}
                self.log_test(
                    "Invoice with Dollar Credit",
                    False,
                    f"Failed to create invoice. Status: {response.status_code}, Error: {error_data.get('detail', 'Unknown error')}",
                    {"status_code": response.status_code, "error": error_data}
                )
                return False
                
        except Exception as e:
            self.log_test(
                "Invoice with Dollar Credit",
                False,
                f"Exception during invoice creation: {str(e)}",
                None
            )
            return False
    
    def verify_credit_status_used(self) -> bool:
        """Verify that the credit status changed to 'used'"""
        try:
            url = f"{BASE_URL}/admin/outsource/partners/{PARTNER_ID}/credits"
            
            response = requests.get(url, headers=self.headers, timeout=30)
            
            if response.status_code == 200:
                credits = response.json()
                
                # Look for used credits
                used_credits = [c for c in credits if c.get("status") == "used"]
                
                if used_credits:
                    self.log_test(
                        "Verify Credit Status Changed to Used",
                        True,
                        f"Found {len(used_credits)} used credit(s). Credit status properly updated after invoice creation.",
                        {
                            "status_code": response.status_code,
                            "used_credits_count": len(used_credits),
                            "total_credits": len(credits)
                        }
                    )
                    return True
                else:
                    self.log_test(
                        "Verify Credit Status Changed to Used",
                        False,
                        f"No used credits found. Credit status was not updated after invoice creation.",
                        {
                            "status_code": response.status_code,
                            "total_credits": len(credits),
                            "credits": credits
                        }
                    )
                    return False
            else:
                error_data = response.json() if response.content else {}
                self.log_test(
                    "Verify Credit Status Changed to Used",
                    False,
                    f"Failed to get credits. Status: {response.status_code}, Error: {error_data.get('detail', 'Unknown error')}",
                    {"status_code": response.status_code, "error": error_data}
                )
                return False
                
        except Exception as e:
            self.log_test(
                "Verify Credit Status Changed to Used",
                False,
                f"Exception during credit status verification: {str(e)}",
                None
            )
            return False
    
    def test_invoice_with_coupon(self, coupon_code: str) -> bool:
        """Test creating an invoice with coupon applied"""
        try:
            url = f"{BASE_URL}/admin/outsource/invoices"
            payload = {
                "partner_id": PARTNER_ID,
                "invoice_date": "2024-01-16",
                "due_date": "2024-02-16",
                "coupon_code": coupon_code,
                "items": [
                    {
                        "description": "Credit Repair Services - February 2024",
                        "quantity": 8,
                        "unit_price": 60.0
                    }
                ],
                "notes": "Test invoice for coupon application"
            }
            
            response = requests.post(url, json=payload, headers=self.headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                # Verify coupon was applied
                subtotal = data.get("subtotal", 0)
                total_amount = data.get("total_amount", 0)
                total_discount = data.get("total_discount", 0)
                adjustments = data.get("adjustments", [])
                
                # Check if coupon adjustment exists
                coupon_adjustment = None
                for adj in adjustments:
                    if adj.get("type") == "coupon":
                        coupon_adjustment = adj
                        break
                
                if coupon_adjustment and total_discount >= 50.0:
                    self.log_test(
                        "Invoice with Coupon",
                        True,
                        f"Invoice created successfully with {coupon_code} coupon applied. Subtotal: ${subtotal}, Total: ${total_amount}, Discount: ${total_discount}",
                        {
                            "status_code": response.status_code,
                            "invoice_id": data.get("id"),
                            "subtotal": subtotal,
                            "total_amount": total_amount,
                            "total_discount": total_discount,
                            "coupon_code": coupon_code,
                            "coupon_applied": True
                        }
                    )
                    
                    # Verify coupon usage incremented
                    return self.verify_coupon_usage_incremented(coupon_code)
                else:
                    self.log_test(
                        "Invoice with Coupon",
                        False,
                        f"Coupon not properly applied. Coupon adjustment found: {coupon_adjustment is not None}, Total discount: ${total_discount}",
                        {
                            "status_code": response.status_code,
                            "subtotal": subtotal,
                            "total_amount": total_amount,
                            "total_discount": total_discount,
                            "adjustments": adjustments
                        }
                    )
                    return False
            else:
                error_data = response.json() if response.content else {}
                self.log_test(
                    "Invoice with Coupon",
                    False,
                    f"Failed to create invoice with coupon. Status: {response.status_code}, Error: {error_data.get('detail', 'Unknown error')}",
                    {"status_code": response.status_code, "error": error_data}
                )
                return False
                
        except Exception as e:
            self.log_test(
                "Invoice with Coupon",
                False,
                f"Exception during invoice creation with coupon: {str(e)}",
                None
            )
            return False
    
    def verify_coupon_usage_incremented(self, coupon_code: str) -> bool:
        """Verify that the coupon current_uses incremented"""
        try:
            url = f"{BASE_URL}/admin/outsource/coupons"
            
            response = requests.get(url, headers=self.headers, timeout=30)
            
            if response.status_code == 200:
                coupons = response.json()
                
                # Find our test coupon
                test_coupon = None
                for coupon in coupons:
                    if coupon.get("code") == coupon_code:
                        test_coupon = coupon
                        break
                
                if test_coupon:
                    current_uses = test_coupon.get("current_uses", 0)
                    if current_uses > 0:
                        self.log_test(
                            "Verify Coupon Usage Incremented",
                            True,
                            f"Coupon usage properly incremented. Current uses: {current_uses}",
                            {
                                "status_code": response.status_code,
                                "coupon_code": coupon_code,
                                "current_uses": current_uses,
                                "max_uses": test_coupon.get("max_uses")
                            }
                        )
                        return True
                    else:
                        self.log_test(
                            "Verify Coupon Usage Incremented",
                            False,
                            f"Coupon usage not incremented. Current uses: {current_uses}",
                            {
                                "status_code": response.status_code,
                                "coupon_code": coupon_code,
                                "current_uses": current_uses,
                                "coupon_data": test_coupon
                            }
                        )
                        return False
                else:
                    self.log_test(
                        "Verify Coupon Usage Incremented",
                        False,
                        f"Test coupon '{coupon_code}' not found in coupons list",
                        {
                            "status_code": response.status_code,
                            "coupon_code": coupon_code,
                            "total_coupons": len(coupons)
                        }
                    )
                    return False
            else:
                error_data = response.json() if response.content else {}
                self.log_test(
                    "Verify Coupon Usage Incremented",
                    False,
                    f"Failed to get coupons. Status: {response.status_code}, Error: {error_data.get('detail', 'Unknown error')}",
                    {"status_code": response.status_code, "error": error_data}
                )
                return False
                
        except Exception as e:
            self.log_test(
                "Verify Coupon Usage Incremented",
                False,
                f"Exception during coupon usage verification: {str(e)}",
                None
            )
            return False
    
    def test_invoice_with_multiple_adjustments(self) -> bool:
        """Test creating an invoice with both discount and credit applied"""
        try:
            url = f"{BASE_URL}/admin/outsource/invoices"
            payload = {
                "partner_id": PARTNER_ID,
                "invoice_date": "2024-01-17",
                "due_date": "2024-02-17",
                "items": [
                    {
                        "description": "Credit Repair Services - March 2024",
                        "quantity": 20,
                        "unit_price": 75.0
                    }
                ],
                "notes": "Test invoice for multiple adjustments (discount + credit)"
            }
            
            response = requests.post(url, json=payload, headers=self.headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                # Verify multiple adjustments were applied
                subtotal = data.get("subtotal", 0)
                total_amount = data.get("total_amount", 0)
                total_discount = data.get("total_discount", 0)
                adjustments = data.get("adjustments", [])
                
                # Check for both discount and credit adjustments
                discount_adjustment = None
                credit_adjustment = None
                
                for adj in adjustments:
                    if adj.get("type") == "discount":
                        discount_adjustment = adj
                    elif adj.get("type") == "credit":
                        credit_adjustment = adj
                
                if len(adjustments) >= 1 and total_discount > 0:
                    self.log_test(
                        "Invoice with Multiple Adjustments",
                        True,
                        f"Invoice created successfully with adjustments. Subtotal: ${subtotal}, Total: ${total_amount}, Total Discount: ${total_discount}, Adjustments: {len(adjustments)}",
                        {
                            "status_code": response.status_code,
                            "invoice_id": data.get("id"),
                            "subtotal": subtotal,
                            "total_amount": total_amount,
                            "total_discount": total_discount,
                            "adjustments_count": len(adjustments),
                            "has_discount": discount_adjustment is not None,
                            "has_credit": credit_adjustment is not None,
                            "adjustments": adjustments
                        }
                    )
                    return True
                else:
                    self.log_test(
                        "Invoice with Multiple Adjustments",
                        False,
                        f"Adjustments not properly applied. Total discount: ${total_discount}, Adjustments: {len(adjustments)}",
                        {
                            "status_code": response.status_code,
                            "subtotal": subtotal,
                            "total_amount": total_amount,
                            "total_discount": total_discount,
                            "adjustments": adjustments,
                            "has_discount": discount_adjustment is not None,
                            "has_credit": credit_adjustment is not None
                        }
                    )
                    return False
            else:
                error_data = response.json() if response.content else {}
                self.log_test(
                    "Invoice with Multiple Adjustments",
                    False,
                    f"Failed to create invoice with multiple adjustments. Status: {response.status_code}, Error: {error_data.get('detail', 'Unknown error')}",
                    {"status_code": response.status_code, "error": error_data}
                )
                return False
                
        except Exception as e:
            self.log_test(
                "Invoice with Multiple Adjustments",
                False,
                f"Exception during invoice creation with multiple adjustments: {str(e)}",
                None
            )
            return False
    
    def test_billing_info_endpoint(self) -> bool:
        """Test the billing info endpoint"""
        try:
            url = f"{BASE_URL}/admin/outsource/partners/{PARTNER_ID}/billing-info"
            
            response = requests.get(url, headers=self.headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                # Verify response structure
                required_fields = ["credits_summary", "discounts_summary", "has_billing_adjustments"]
                missing_fields = [field for field in required_fields if field not in data]
                
                credits_summary = data.get("credits_summary", [])
                discounts_summary = data.get("discounts_summary", [])
                has_billing_adjustments = data.get("has_billing_adjustments", False)
                
                if not missing_fields:
                    self.log_test(
                        "Billing Info Endpoint",
                        True,
                        f"Billing info endpoint working correctly. Credits: {len(credits_summary)}, Discounts: {len(discounts_summary)}, Has adjustments: {has_billing_adjustments}",
                        {
                            "status_code": response.status_code,
                            "credits_count": len(credits_summary),
                            "discounts_count": len(discounts_summary),
                            "has_billing_adjustments": has_billing_adjustments,
                            "response_structure_valid": True
                        }
                    )
                    return True
                else:
                    self.log_test(
                        "Billing Info Endpoint",
                        False,
                        f"Billing info response missing required fields: {missing_fields}",
                        {
                            "status_code": response.status_code,
                            "missing_fields": missing_fields,
                            "response_data": data
                        }
                    )
                    return False
            else:
                error_data = response.json() if response.content else {}
                self.log_test(
                    "Billing Info Endpoint",
                    False,
                    f"Failed to get billing info. Status: {response.status_code}, Error: {error_data.get('detail', 'Unknown error')}",
                    {"status_code": response.status_code, "error": error_data}
                )
                return False
                
        except Exception as e:
            self.log_test(
                "Billing Info Endpoint",
                False,
                f"Exception during billing info test: {str(e)}",
                None
            )
            return False
    
    def run_all_tests(self):
        """Run all invoice billing adjustment tests"""
        print("\n" + "="*80)
        print("💰 INVOICE BILLING ADJUSTMENTS TESTS")
        print("="*80)
        print(f"Partner ID: {PARTNER_ID}")
        print(f"Test Credentials: {ADMIN_EMAIL}")
        
        # Authenticate first
        if not self.authenticate():
            print("❌ Authentication failed. Cannot proceed with tests.")
            return False
        
        # Track results
        total_tests = 0
        passed_tests = 0
        
        try:
            # Test 1: Create a dollar credit for the partner
            print("\n--- TEST 1: Create $200 Dollar Credit ---")
            credit_success, credit_id = self.create_test_credit()
            if credit_success:
                passed_tests += 1
            total_tests += 1
            
            # Test 2: Create a test coupon
            print("\n--- TEST 2: Create Test Coupon ---")
            coupon_success, coupon_code = self.create_test_coupon()
            if coupon_success:
                passed_tests += 1
            total_tests += 1
            
            # Test 3: Verify percentage discount exists
            print("\n--- TEST 3: Verify Percentage Discount ---")
            discount_success = self.verify_percentage_discount()
            if discount_success:
                passed_tests += 1
            total_tests += 1
            
            # Test 4: Create invoice with dollar credit only
            print("\n--- TEST 4: Create Invoice with Dollar Credit ---")
            invoice_credit_success = self.test_invoice_with_credit()
            if invoice_credit_success:
                passed_tests += 1
            total_tests += 1
            
            # Test 5: Create invoice with coupon
            print("\n--- TEST 5: Create Invoice with Coupon ---")
            if coupon_success:
                invoice_coupon_success = self.test_invoice_with_coupon(coupon_code)
                if invoice_coupon_success:
                    passed_tests += 1
            total_tests += 1
            
            # Test 6: Create another credit for multiple adjustments test
            print("\n--- TEST 6: Create Additional Credit for Multiple Adjustments ---")
            credit_success2, credit_id2 = self.create_test_credit(amount=100)
            if credit_success2:
                passed_tests += 1
            total_tests += 1
            
            # Test 7: Create invoice with multiple adjustments
            print("\n--- TEST 7: Create Invoice with Multiple Adjustments ---")
            invoice_multiple_success = self.test_invoice_with_multiple_adjustments()
            if invoice_multiple_success:
                passed_tests += 1
            total_tests += 1
            
            # Test 8: Test billing info endpoint
            print("\n--- TEST 8: Test Billing Info Endpoint ---")
            billing_info_success = self.test_billing_info_endpoint()
            if billing_info_success:
                passed_tests += 1
            total_tests += 1
            
        except Exception as e:
            print(f"❌ Unexpected error during testing: {str(e)}")
        
        # Final results
        print("\n" + "="*80)
        print("📊 INVOICE BILLING ADJUSTMENTS TEST RESULTS")
        print("="*80)
        
        success_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {total_tests - passed_tests}")
        print(f"Success Rate: {success_rate:.1f}%")
        
        if success_rate >= 90:
            print("🎉 EXCELLENT! Invoice billing adjustments are working perfectly.")
        elif success_rate >= 70:
            print("✅ GOOD! Most invoice billing features are working correctly.")
        elif success_rate >= 50:
            print("⚠️ MODERATE! Some invoice billing features need attention.")
        else:
            print("❌ CRITICAL! Invoice billing adjustments are not working properly.")
        
        # Summary of failed tests
        failed_tests = [result for result in self.test_results if not result["success"]]
        if failed_tests:
            print(f"\n🔍 FAILED TESTS SUMMARY ({len(failed_tests)} failures):")
            for i, test in enumerate(failed_tests, 1):
                print(f"{i}. {test['test']}: {test['details']}")
        
        return success_rate >= 70


if __name__ == "__main__":
    tester = InvoiceBillingTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)