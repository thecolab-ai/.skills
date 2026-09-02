#!/usr/bin/env python3
"""Current Woolworths NZ GraphQL product and trolley contracts.

The query documents are deliberately limited to catalogue browsing, pricing,
purchase-unit, and trolley workflows.
"""

from __future__ import annotations

import math
from typing import Any

GRAPHQL_PATH = "/api/graphql"
PUBLIC_OPERATIONS = frozenset(
    {"ProductSearch", "GetProductDetails", "GetAllCategories"}
)
ACCOUNT_QUERY_OPERATIONS = frozenset({"CustomerCart"})
ACCOUNT_MUTATION_OPERATIONS = frozenset({"SetCartLineItemQuantity", "ClearCart"})

PRODUCT_FIELDS = """
    __typename
    sku
    productName
    slug
    imageUrl
    storeKey
    brand
    categoryHierarchyNames { lvl0 lvl1 lvl2 lvl3 }
    variants {
      variantKey
      name
      unitOfMeasure
      purchaseUnit { unit }
      variantPrice {
        currency
        isSpecial
        isClubPrice
        isBoostOffer
        sellingUnit
        sellingPrice
        savedAmount
        wasPrice
        cupPrice
        cupUnit
      }
    }
"""

PRODUCT_SEARCH_QUERY = f"""
query ProductSearch($searchInput: CompositeSearchInput!) {{
  My {{
    products(searchInput: $searchInput) {{
      results {{
        ... on ProductSummary {{ {PRODUCT_FIELDS} }}
        ... on SponsoredProduct {{ {PRODUCT_FIELDS} }}
      }}
      totalCount
      pageSize
      totalPages
      currentPage
    }}
  }}
}}
""".strip()

PRODUCT_DETAIL_QUERY = """
query GetProductDetails($key: String!) {
  My {
    product(key: $key) {
      key
      brand
      slug
      name
      isLiquor
      isOwnBrand
      isTobacco
      storeId
      taxPercent
      metaTitle
      metaDescription
      richDescription
      category {
        name key slug displaySlug level
        parent {
          name key slug displaySlug level
          parent { name key slug displaySlug level }
        }
      }
      assets { name contentType url altText }
      tags {
        content {
          roundel { zone imageUrl alt url }
          strap { type label secondaryLabel url scheme zone }
        }
        priority type kind
      }
      variants {
        __typename
        ... on GroceryVariant {
          key sku richDescription name countryOfOrigin tgaWarnings productWarnings
          slug barcode servingsPerPack servingSize ingredients directionsOfUse
          allergenContained ageRestriction volumeSize
          nutritionalInformation {
            energy protein fatTotal fatTotalSaturated carbohydrate
            carbohydrateSugars dietaryFibre sodium quantityPerUnit
          }
          assets { name contentType url altText }
          purchasingUnits { unit }
          variantPrice {
            priceKey currency isClubPrice isSpecial isBoostOffer sellingPrice
            sellingUnit cupPrice cupUnit discountPrice savedAmount wasPrice
          }
        }
        ... on RegulatedVariant {
          key sku richDescription name countryOfOrigin tgaWarnings productWarnings
          slug barcode servingsPerPack servingSize ingredients directionsOfUse
          allergenContained ageRestriction volumeSize
          nutritionalInformation {
            energy protein fatTotal fatTotalSaturated carbohydrate
            carbohydrateSugars dietaryFibre sodium quantityPerUnit
          }
          assets { name contentType url altText }
          purchasingUnits { unit }
          variantPrice {
            priceKey currency isClubPrice isSpecial isBoostOffer sellingPrice
            sellingUnit cupPrice cupUnit discountPrice savedAmount wasPrice
          }
        }
        ... on GeneralMerchandiseVariant {
          key sku richDescription name countryOfOrigin tgaWarnings productWarnings
          slug barcode directionsOfUse allergenContained
          ageRestriction volumeSize
          assets { name contentType url altText }
          purchasingUnits { unit }
          variantPrice {
            priceKey currency isClubPrice isSpecial isBoostOffer sellingPrice
            sellingUnit cupPrice cupUnit discountPrice savedAmount wasPrice
          }
        }
        ... on MonetaryVariant {
          key sku richDescription name countryOfOrigin tgaWarnings productWarnings
          slug directionsOfUse ageRestriction volumeSize
          assets { name contentType url altText }
          purchasingUnits { unit }
          variantPrice {
            priceKey currency isClubPrice isSpecial isBoostOffer sellingPrice
            sellingUnit cupPrice cupUnit discountPrice savedAmount wasPrice
          }
        }
      }
    }
  }
}
""".strip()

CATEGORIES_QUERY = """
query GetAllCategories($categoryKey: String) {
  My {
    categories(categoryKey: $categoryKey) {
      name level key imageUrl displayOrder description slug displaySlug
      children {
        name level key imageUrl displayOrder description slug displaySlug
        children {
          name level key imageUrl displayOrder description slug displaySlug
          children {
            name level key imageUrl displayOrder description slug displaySlug
          }
        }
      }
    }
  }
}
""".strip()

CART_FIELDS = """
    key
    cartState
    totalItemQuantity
    totalUniqueProductSku
    shoppingMode { mode pickupLocationId }
    validationResult {
      isValid
      failedValidations { ruleName message affectedSkus resolution title }
    }
    lineItems {
      sku
      productVariantSku
      quantity
      product {
        name
        slug
        brand
        variants {
          ... on GroceryVariant { key purchasingUnits { unit } }
          ... on RegulatedVariant { key purchasingUnits { unit } }
          ... on GeneralMerchandiseVariant { key purchasingUnits { unit } }
          ... on MonetaryVariant { key purchasingUnits { unit } }
          ... on NonMerchandiseVariant { key purchasingUnits { unit } }
        }
      }
      unitPrice { beforeDiscountAsCents afterDiscountAsCents }
      lineTotal { afterDiscountAsCents discountAmountAsCents }
    }
    pricing {
      orderSubtotal {
        beforeDiscountAsCents afterDiscountAsCents discountAmountAsCents
      }
      productSubtotal {
        beforeDiscountAsCents afterDiscountAsCents discountAmountAsCents
      }
      total { beforeDiscountAsCents afterDiscountAsCents discountAmountAsCents }
    }
"""

CUSTOMER_CART_QUERY = f"""
query CustomerCart {{
  customerCart {{ {CART_FIELDS} }}
}}
""".strip()

SET_CART_QUANTITY_MUTATION = f"""
mutation SetCartLineItemQuantity($input: SetCartLineItemQuantitiesInput!) {{
  setCartLineItemQuantity(input: $input) {{ {CART_FIELDS} }}
}}
""".strip()

CLEAR_CART_MUTATION = f"""
mutation ClearCart {{
  clearCart {{ {CART_FIELDS} }}
}}
""".strip()


class GraphQLContractError(ValueError):
    """Raised when a response does not match the expected website contract."""


def _errors(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["response is not a JSON object"]
    errors = payload.get("errors")
    if not isinstance(errors, list):
        return []
    messages: list[str] = []
    for error in errors:
        if isinstance(error, dict) and error.get("message"):
            messages.append(str(error["message"]))
        else:
            messages.append(str(error))
    return messages


def require_graphql_data(payload: Any) -> dict[str, Any]:
    messages = _errors(payload)
    if messages:
        raise GraphQLContractError("; ".join(messages))
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise GraphQLContractError("GraphQL response omitted data")
    return data


def product_search_request(
    *, mode: str, value: str | None, page: int, limit: int
) -> dict[str, Any]:
    if page < 1:
        raise ValueError("page must be at least 1")
    if not 1 <= limit <= 48:
        raise ValueError("limit must be between 1 and 48")
    common: dict[str, Any] = {
        "pageIndex": page - 1,
        "pageSize": limit,
        "facetFilters": [],
        "staticFilters": [],
        "sortBy": "RELEVANCE",
    }
    if mode == "keyword":
        if not value:
            raise ValueError("keyword search requires a value")
        common["value"] = value
        search_input = {"byKeyword": common}
    elif mode == "category":
        if not value:
            raise ValueError("category search requires a key")
        common["value"] = value
        search_input = {"byCategoryKey": common}
    elif mode == "specials":
        search_input = {"byProductPromotionSpecials": common}
    elif mode == "keyword-specials":
        if not value:
            raise ValueError("specials search requires a value")
        common["value"] = value
        common["staticFilters"] = ["SPECIALS"]
        search_input = {"byKeyword": common}
    else:
        raise ValueError(f"unsupported product search mode: {mode}")
    return {
        "operationName": "ProductSearch",
        "query": PRODUCT_SEARCH_QUERY,
        "variables": {"searchInput": search_input},
    }


def product_detail_request(key: str) -> dict[str, Any]:
    if not str(key).strip():
        raise ValueError("product key is required")
    return {
        "operationName": "GetProductDetails",
        "query": PRODUCT_DETAIL_QUERY,
        "variables": {"key": str(key).strip()},
    }


def categories_request(category_key: str | None = None) -> dict[str, Any]:
    return {
        "operationName": "GetAllCategories",
        "query": CATEGORIES_QUERY,
        "variables": {"categoryKey": category_key or None},
    }


def customer_cart_request() -> dict[str, Any]:
    return {
        "operationName": "CustomerCart",
        "query": CUSTOMER_CART_QUERY,
        "variables": {},
    }


def cart_quantity_request(variant_key: str, quantity: float) -> dict[str, Any]:
    key = str(variant_key).strip()
    if not key:
        raise ValueError("variant key is required")
    try:
        numeric_quantity = float(quantity)
    except (TypeError, ValueError) as exc:
        raise ValueError("trolley quantity must be numeric") from exc
    if not math.isfinite(numeric_quantity) or numeric_quantity < 0:
        raise ValueError("trolley quantity must be finite and non-negative")
    return {
        "operationName": "SetCartLineItemQuantity",
        "query": SET_CART_QUANTITY_MUTATION,
        "variables": {
            "input": {
                "cartLineItemQuantityUpdates": [
                    {"variantKey": key, "quantity": quantity}
                ]
            }
        },
    }


def clear_cart_request() -> dict[str, Any]:
    return {
        "operationName": "ClearCart",
        "query": CLEAR_CART_MUTATION,
        "variables": {},
    }


def _category_label(hierarchy: Any) -> str:
    if not isinstance(hierarchy, dict):
        return ""
    return " / ".join(
        str(hierarchy[key])
        for key in ("lvl0", "lvl1", "lvl2", "lvl3")
        if hierarchy.get(key)
    )


def _first_variant(item: dict[str, Any]) -> dict[str, Any]:
    variants = item.get("variants")
    if not isinstance(variants, list):
        return {}
    return next((variant for variant in variants if isinstance(variant, dict)), {})


def parse_product_summary(item: dict[str, Any]) -> dict[str, Any]:
    variant = _first_variant(item)
    price = variant.get("variantPrice") or {}
    purchase = variant.get("purchaseUnit") or {}
    sale_price = price.get("sellingPrice")
    original_price = price.get("wasPrice")
    if original_price is None:
        original_price = sale_price
    sku = str(item.get("sku") or variant.get("variantKey") or "")
    slug = str(item.get("slug") or "")
    return {
        "sku": sku,
        "variant_key": variant.get("variantKey"),
        "name": item.get("productName") or variant.get("name") or "",
        "brand": item.get("brand") or "",
        "size": variant.get("name") or "",
        "package_type": "",
        "price": original_price,
        "sale_price": sale_price,
        "is_special": bool(price.get("isSpecial")),
        "is_club_price": bool(price.get("isClubPrice")),
        "save_price": price.get("savedAmount"),
        "currency": price.get("currency") or "NZD",
        "cup_price": price.get("cupPrice"),
        "cup_measure": price.get("cupUnit"),
        "unit": purchase.get("unit") or variant.get("unitOfMeasure"),
        "category": _category_label(item.get("categoryHierarchyNames")),
        "image": item.get("imageUrl"),
        "store_key": item.get("storeKey"),
        "url": f"https://www.woolworths.co.nz/shop/product-details/{sku}/{slug}",
    }


def parse_product_search(payload: Any) -> dict[str, Any]:
    data = require_graphql_data(payload)
    products = (data.get("My") or {}).get("products") or {}
    results = products.get("results")
    if not isinstance(results, list):
        raise GraphQLContractError("ProductSearch response omitted results")
    records = [
        parse_product_summary(item)
        for item in results
        if isinstance(item, dict)
        and item.get("__typename") in {"ProductSummary", "SponsoredProduct"}
    ]
    return {
        "products": records,
        "count": len(records),
        "total": products.get("totalCount"),
        "page": (products.get("currentPage") or 0) + 1,
        "page_size": products.get("pageSize"),
        "total_pages": products.get("totalPages"),
    }


def _category_path(category: Any) -> str:
    parts: list[str] = []
    current = category
    while isinstance(current, dict):
        if current.get("name"):
            parts.append(str(current["name"]))
        current = current.get("parent")
    return " / ".join(reversed(parts))


def _purchasing_unit(variant: dict[str, Any]) -> dict[str, Any]:
    units = variant.get("purchasingUnits")
    if isinstance(units, dict):
        return units
    if isinstance(units, list):
        return next((item for item in units if isinstance(item, dict)), {})
    purchase = variant.get("purchaseUnit")
    return purchase if isinstance(purchase, dict) else {}


def variant_options(variants: Any) -> list[dict[str, Any]]:
    options = []
    for variant in variants if isinstance(variants, list) else []:
        if not isinstance(variant, dict) or not variant.get("key"):
            continue
        options.append(
            {
                "variant_key": variant.get("key"),
                "variant_sku": variant.get("sku"),
                "unit": _purchasing_unit(variant).get("unit"),
                "name": variant.get("name") or "",
            }
        )
    return options


def parse_product_detail(payload: Any) -> dict[str, Any]:
    data = require_graphql_data(payload)
    product = (data.get("My") or {}).get("product")
    if not isinstance(product, dict):
        raise GraphQLContractError("GetProductDetails response omitted product")
    variants = product.get("variants")
    if not isinstance(variants, list) or not variants:
        raise GraphQLContractError("GetProductDetails response omitted variants")
    variant = next((item for item in variants if isinstance(item, dict)), {})
    price = variant.get("variantPrice") or {}
    purchase = _purchasing_unit(variant)
    assets = variant.get("assets") or product.get("assets") or []
    image = next(
        (
            item.get("url")
            for item in assets
            if isinstance(item, dict) and item.get("url")
        ),
        None,
    )
    sku = str(product.get("key") or variant.get("sku") or "")
    slug = str(variant.get("slug") or product.get("slug") or "")
    selling_price = price.get("sellingPrice")
    return {
        "sku": sku,
        "variant_sku": variant.get("sku"),
        "variant_key": variant.get("key"),
        "name": product.get("name") or variant.get("name") or "",
        "brand": product.get("brand") or "",
        "description": variant.get("richDescription") or product.get("richDescription"),
        "price": price.get("wasPrice")
        if price.get("wasPrice") is not None
        else selling_price,
        "sale_price": selling_price,
        "is_special": bool(price.get("isSpecial")),
        "is_club_price": bool(price.get("isClubPrice")),
        "save_price": price.get("savedAmount"),
        "currency": price.get("currency") or "NZD",
        "cup_price": price.get("cupPrice"),
        "cup_measure": price.get("cupUnit"),
        "unit": purchase.get("unit"),
        "variants": variant_options(variants),
        "category": _category_path(product.get("category")),
        "image": image,
        "store_key": product.get("storeId"),
        "barcode": variant.get("barcode"),
        "country_of_origin": variant.get("countryOfOrigin"),
        "ingredients": variant.get("ingredients"),
        "allergens": variant.get("allergenContained"),
        "nutrition": variant.get("nutritionalInformation"),
        "servings_per_pack": variant.get("servingsPerPack"),
        "serving_size": variant.get("servingSize"),
        "directions": variant.get("directionsOfUse"),
        "warnings": variant.get("productWarnings") or variant.get("tgaWarnings"),
        "url": f"https://www.woolworths.co.nz/shop/product-details/{sku}/{slug}",
    }


def _money(cents: Any) -> float | None:
    if cents is None:
        return None
    try:
        return round(float(cents) / 100, 2)
    except (TypeError, ValueError):
        return None


def parse_customer_cart(
    payload: Any, *, mutation_field: str | None = None
) -> dict[str, Any]:
    data = require_graphql_data(payload)
    field = mutation_field or "customerCart"
    cart = data.get(field)
    if not isinstance(cart, dict):
        raise GraphQLContractError(f"{field} response omitted trolley")
    items = []
    for item in cart.get("lineItems") or []:
        if not isinstance(item, dict):
            continue
        product = item.get("product") or {}
        selected_variant_key = item.get("productVariantSku")
        selected_variant = next(
            (
                option
                for option in variant_options(product.get("variants"))
                if option.get("variant_key") == selected_variant_key
            ),
            {},
        )
        unit_price = item.get("unitPrice") or {}
        line_total = item.get("lineTotal") or {}
        items.append(
            {
                "sku": item.get("sku"),
                "variant_key": item.get("productVariantSku"),
                "quantity": item.get("quantity"),
                "unit": selected_variant.get("unit"),
                "name": product.get("name") or product.get("slug") or "",
                "brand": product.get("brand") or "",
                "unit_price": _money(unit_price.get("afterDiscountAsCents")),
                "line_total": _money(line_total.get("afterDiscountAsCents")),
            }
        )
    pricing = cart.get("pricing") or {}
    product_subtotal = pricing.get("productSubtotal") or {}
    order_subtotal = pricing.get("orderSubtotal") or {}
    validation = cart.get("validationResult") or {}
    shopping_mode = cart.get("shoppingMode") or {}
    return {
        "cart_key": cart.get("key"),
        "item_count": cart.get("totalItemQuantity") or 0,
        "unique_products": cart.get("totalUniqueProductSku") or 0,
        "shopping_mode": shopping_mode.get("mode"),
        "pickup_location_id": shopping_mode.get("pickupLocationId"),
        "items": items,
        "product_subtotal": _money(product_subtotal.get("afterDiscountAsCents")),
        "order_subtotal": _money(order_subtotal.get("afterDiscountAsCents")),
        "valid": validation.get("isValid"),
        "validation_issues": validation.get("failedValidations") or [],
    }


def parse_categories(payload: Any) -> dict[str, Any]:
    data = require_graphql_data(payload)
    root = (data.get("My") or {}).get("categories")
    if not isinstance(root, dict):
        raise GraphQLContractError("GetAllCategories response omitted categories")
    return root
